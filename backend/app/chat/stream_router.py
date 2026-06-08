"""SSE 流式对话路由

POST /api/chat/stream — Server-Sent Events 流式对话端点。
使用 graph.astream(stream_mode=["updates","messages"]) 驱动 Agent StateGraph：
- updates 事件：节点完成时推送 thinking/status/sources
- messages 事件：respond 节点内 LLM 逐 token 流式输出
respond 节点在 graph 内部调用 ChatOpenAI，PostgresSaver 自动保存 AIMessage checkpoint。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from langchain_core.messages import HumanMessage

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.dependencies import get_graph, get_checkpointer, get_db
from app.chat.errors import ChatErrorCode, ConversationErrorCode, make_error, make_conversation_error
from app.chat.schemas import ChatRequest, StopRequest, StatusPayload
from app.chat.conversation_utils import load_conversation_by_id, to_api_message
from app.domain.models import Conversation
from app.infra.conversation_repo import ConversationRepo
from app.middleware.auth import UserContext, get_current_user

router = APIRouter(prefix="/api", tags=["chat"])

logger = logging.getLogger(__name__)


# ========== 数据结构和注册表 ==========

_GRAPH_DONE = object()   # sentinel: graph 正常完成
_GRAPH_ERROR = object()  # sentinel: graph 发生错误


@dataclass
class _TitleEvent:
    """标题生成完成事件，推送到 SSE 流"""
    conversation_id: str
    title: str


@dataclass
class GraphTaskInfo:
    """活跃 graph 任务信息"""
    queue: asyncio.Queue           # 事件队列
    cancel_event: asyncio.Event    # 停止信号
    task: asyncio.Task | None      # 后台任务引用


# 活跃 graph 注册表：conversation_id -> GraphTaskInfo
_active_graphs: dict[str, GraphTaskInfo] = {}


# ========== 后台任务函数 ==========


async def _run_graph(
    graph,
    input_state: dict,
    config: dict,
    queue: asyncio.Queue,
    cancel_event: asyncio.Event,
    db: AsyncSession,
    conversation_id: str,
    user: UserContext,
    question: str,
    is_new: bool,
    app_state,
) -> None:
    """后台任务：迭代 graph.astream()，put 事件到 queue

    图执行完成后（非取消）会执行：
    - update_message_stats: 更新对话统计
    - 标题生成：新对话时生成标题
    """
    cancelled = False
    try:
        async with asyncio.timeout(300):  # 5 分钟硬上限
            async for event in graph.astream(
                input_state,
                config=config,
                stream_mode=["updates", "messages"],
            ):
                if cancel_event.is_set():
                    logger.info(f"[stream] cancelled by user: {conversation_id}")
                    cancelled = True
                    break
                await queue.put(event)
    except TimeoutError:
        logger.warning(f"[stream] graph timeout: {conversation_id}")
        await queue.put(_GRAPH_ERROR)
    except Exception as e:
        logger.error(f"[stream] graph error: {e}", exc_info=True)
        await queue.put(_GRAPH_ERROR)
        return
    else:
        # 正常完成（未超时、未异常、未取消）
        if not cancelled:
            # 完成后更新统计
            try:
                await ConversationRepo.update_message_stats(db, conversation_id)
                await db.commit()
            except Exception as e:
                logger.warning(f"[stream] update_message_stats failed: {e}")

            # 标题生成：新对话时生成标题并推送 SSE title 事件
            if is_new:
                try:
                    title = await app_state.generator.generate_title(question)
                    if title:
                        await ConversationRepo.update(db, conversation_id, user.user_id, title=title)
                        await db.commit()
                        await queue.put(_TitleEvent(conversation_id=conversation_id, title=title))
                except Exception as e:
                    logger.warning(f"[stream] title generation failed: {e}")

            await queue.put(_GRAPH_DONE)
    finally:
        # 从注册表移除
        _active_graphs.pop(conversation_id, None)


async def _run_with_recognition(
    graph,
    body: ChatRequest,
    config: dict,
    queue: asyncio.Queue,
    cancel_event: asyncio.Event,
    db: AsyncSession,
    conversation_id: str,
    user: UserContext,
    is_new: bool,
    app_state,
) -> None:
    """含 VLM 图片识别的后台任务：recognizing → VLM → Graph"""
    recognized_text = ""
    image_refs_kwargs: list[dict] = []

    # 1. SSE status: recognizing
    await queue.put(_sse_frame("status", {"stage": "recognizing", "message": "正在识别图片..."}))

    # 2. 调 VLM（30s 超时），失败降级纯文字
    try:
        recognition_provider = app_state.recognition_provider
        recognized_text = await asyncio.wait_for(
            recognition_provider.recognize(
                [img.url for img in body.images], body.question
            ),
            timeout=30,
        )
        # VLM 成功：保留图片元数据引用
        image_refs_kwargs = [{"url": img.url, "image_id": img.image_id} for img in body.images]
    except Exception:
        logger.warning("[stream] Vision LLM failed, degrading to text-only")
        recognized_text = ""

    # 3. 构造 HumanMessage（content 数组：识别文本与用户问题分开存储）
    if recognized_text:
        content = [
            {"type": "text", "text": f"以下是用户上传图片的自动识别结果：\n{recognized_text}"},
            {"type": "text", "text": body.question},
        ]
    else:
        content = body.question
    human_msg = HumanMessage(
        content=content,
        additional_kwargs={"images": image_refs_kwargs} if image_refs_kwargs else {},
    )
    input_state = {"messages": [human_msg], "question": body.question}

    # 4. 启动 Graph（复用现有 _run_graph）
    await _run_graph(
        graph=graph,
        input_state=input_state,
        config=config,
        queue=queue,
        cancel_event=cancel_event,
        db=db,
        conversation_id=conversation_id,
        user=user,
        question=body.question,
        is_new=is_new,
        app_state=app_state,
    )


@router.post("/chat/stream")
async def stream_chat(
    body: ChatRequest,
    http_request: Request,
    graph=Depends(get_graph),
    checkpointer=Depends(get_checkpointer),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """SSE 流式对话端点

    使用 graph.astream(stream_mode=["updates","messages"]) 驱动 Agent StateGraph。
    - updates：summarize/rewrite/retrieve/respond 节点完成时推送状态事件
    - messages：respond 节点内 LLM 逐 token 流式推送
    - respond 节点完成后 PostgresSaver 自动保存 AIMessage
    """
    conversation_id = body.conversation_id or str(uuid.uuid4())
    is_new_conversation = not body.conversation_id

    # 已有 conversation_id：归属校验
    if not is_new_conversation:
        try:
            conv = await ConversationRepo.get_by_id(db, conversation_id, user.user_id)
            if conv is None:
                # 归属校验失败：对话不存在或无权访问
                return StreamingResponse(
                    _single_error_event(make_conversation_error(ConversationErrorCode.NOT_FOUND)),
                    media_type="text/event-stream",
                )
        except Exception as e:
            logger.error(f"[stream] conversation ownership check failed: {e}", exc_info=True)
            return StreamingResponse(
                _single_error_event(make_error(ChatErrorCode.INTERNAL_ERROR)),
                media_type="text/event-stream",
            )

    # 新对话：init 阶段前创建 conversation 记录
    if is_new_conversation:
        conv = Conversation(id=conversation_id, user_id=user.user_id)
        await ConversationRepo.create(db, conv)
        await db.commit()

    config = {
        "configurable": {
            "thread_id": conversation_id,
            "user_id": user.user_id,
        }
    }

    # R019: 图片校验
    if body.images:
        image_manager = http_request.app.state.image_manager
        for img in body.images:
            filepath = image_manager.resolve_filepath(img.url, user.user_id)
            if not os.path.exists(filepath):
                raise HTTPException(400, "图片不存在，请重新上传")

    # ========== 创建后台任务基础设施 ==========
    queue = asyncio.Queue()
    cancel_event = asyncio.Event()
    task_info = GraphTaskInfo(queue=queue, cancel_event=cancel_event, task=None)
    _active_graphs[conversation_id] = task_info

    # R019: 有图片时走识别流程，无图片时走原有流程
    if body.images:
        task = asyncio.create_task(
            _run_with_recognition(
                graph=graph,
                body=body,
                config=config,
                queue=queue,
                cancel_event=cancel_event,
                db=db,
                conversation_id=conversation_id,
                user=user,
                is_new=is_new_conversation,
                app_state=http_request.app.state,
            )
        )
    else:
        # 将用户问题作为 HumanMessage 传入 graph state，checkpointer 自动持久化
        input_state = {
            "messages": [HumanMessage(content=body.question)],
            "question": body.question,
        }
        task = asyncio.create_task(
            _run_graph(
                graph=graph,
                input_state=input_state,
                config=config,
                queue=queue,
                cancel_event=cancel_event,
                db=db,
                conversation_id=conversation_id,
                user=user,
                question=body.question,
                is_new=is_new_conversation,
                app_state=http_request.app.state,
            )
        )
    task_info.task = task

    return StreamingResponse(
        _create_sse_generator(queue, conversation_id, http_request, "SSE stream"),
        media_type="text/event-stream",
    )


async def _map_event_to_sse(event, http_request: Request):
    """将 graph.astream 双流事件映射为 SSE 帧

    双流事件格式：
    - updates: ("updates", {node_name: node_output})
    - messages: ("messages", (AIMessageChunk, metadata))
    """
    if not isinstance(event, tuple) or len(event) != 2:
        return

    stream_type, data = event

    if stream_type == "updates":
        # 节点完成事件 — data 是 {node_name: node_output}
        if not isinstance(data, dict):
            return
        for node_name, node_output in data.items():
            async for frame in _map_node_update_to_sse(node_name, node_output):
                yield frame

    elif stream_type == "messages":
        # LLM token 事件 — data 是 (message_chunk, metadata)
        if not isinstance(data, tuple) or len(data) != 2:
            return
        message_chunk, metadata = data
        # 只推送 respond 节点的 token（其他节点的 messages 事件忽略）
        node_name = metadata.get("langgraph_node", "")
        if node_name == "respond":
            token = getattr(message_chunk, "content", "")
            if token:
                yield _sse_frame("token", token)


async def _map_node_update_to_sse(node_name: str, node_output: dict):
    """将节点完成事件映射为 SSE 帧"""
    if node_name == "summarize":
        summary = node_output.get("conversation_summary") if node_output else None
        if summary:
            yield _sse_frame("thinking", {"text": "上下文已压缩", "index": 0})

    elif node_name == "rewrite":
        rewritten = node_output.get("rewritten_question") if node_output else None
        if rewritten:
            yield _sse_frame("thinking", {"text": f"查询改写: {rewritten}", "index": 1})

    elif node_name == "retrieve":
        yield _sse_frame(
            "status",
            {"stage": "retrieving", "message": "正在检索教材..."},
        )

        sources = node_output.get("sources", []) if node_output else []
        if sources:
            serialized = [_serialize_source(s) for s in sources]
            yield _sse_frame("sources", serialized)

    elif node_name == "respond":
        yield _sse_frame(
            "status",
            {"stage": "generating", "message": "正在生成回答..."},
        )
        # respond 节点完成后，AIMessage 已由 PostgresSaver 自动保存
        # token 级别的事件已通过 messages 流推送，此处无需额外处理


def _sse_frame(event_type: str, data: Any) -> str:
    """构造 SSE 文本帧"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _single_error_event(error: dict):
    """仅 yield 一帧 SSE error 事件的异步生成器"""
    yield _sse_frame("error", error)


def _serialize_source(source) -> dict:
    """序列化 SourceReference 为 dict"""
    if hasattr(source, "model_dump"):
        return source.model_dump()
    if hasattr(source, "__dataclass_fields__"):
        return asdict(source)
    return source


async def _create_sse_generator(
    queue: asyncio.Queue,
    conversation_id: str,
    http_request: Request,
    label: str,
):
    """共享 SSE 事件生成器：从 queue 读取事件并 yield SSE frame

    由 event_generator（stream_chat）和 resume_generator（resume_stream）复用。
    """
    try:
        yield _sse_frame("init", {"conversation_id": conversation_id})

        while True:
            if await http_request.is_disconnected():
                logger.info(f"[stream] client disconnected ({label}): {conversation_id}")
                return

            try:
                event = await asyncio.wait_for(queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                continue

            if event is _GRAPH_DONE:
                yield "event: done\ndata: null\n\n"
                return
            elif event is _GRAPH_ERROR:
                yield _sse_frame("error", make_error(ChatErrorCode.INTERNAL_ERROR))
                return
            elif isinstance(event, _TitleEvent):
                yield _sse_frame("title", {"conversation_id": event.conversation_id, "title": event.title})
                continue
            elif isinstance(event, str):
                # 已完成的 SSE 帧（如 recognizing status），直接输出
                yield event
                continue

            async for frame in _map_event_to_sse(event, http_request):
                yield frame

    except Exception as e:
        logger.error(f"{label} error: {e}", exc_info=True)
        yield _sse_frame("error", make_error(ChatErrorCode.INTERNAL_ERROR))


# ========== SSE 重连端点 (R012-BB002) ==========


@router.get("/chat/stream/resume")
async def resume_stream(
    conversation_id: str = Query(...),
    http_request: Request = None,
    checkpointer=Depends(get_checkpointer),
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """SSE 重连端点

    客户端断线后重连时调用：
    - 后台任务运行中 → 返回 SSE 流（剩余事件）
    - 后台任务已完成 → 返回 JSON（完整消息）
    - 后台任务不存在且无消息 → 返回 204
    """
    # 1. 归属校验
    conv = await ConversationRepo.get_by_id(db, conversation_id, user.user_id)
    if not conv:
        return JSONResponse(
            status_code=404,
            content=make_conversation_error(ConversationErrorCode.NOT_FOUND),
        )

    # 2. 查找活跃后台任务
    task_info = _active_graphs.get(conversation_id)
    if task_info is None:
        # 后台任务已完成，从 checkpoint 返回完整消息
        messages = await load_conversation_by_id(checkpointer, conversation_id, user.user_id)
        if not messages:
            return Response(status_code=204)
        api_messages = [to_api_message(msg, idx) for idx, msg in enumerate(messages)]
        return JSONResponse(
            {"conversation_id": conversation_id, "messages": [m.model_dump() for m in api_messages]}
        )

    # 3. 仍在运行 → SSE 流
    return StreamingResponse(
        _create_sse_generator(task_info.queue, conversation_id, http_request, "Resume stream"),
        media_type="text/event-stream",
    )


# ========== 停止端点 (R012-BB003) ==========


@router.post("/chat/stop")
async def stop_chat(
    body: StopRequest,
    db: AsyncSession = Depends(get_db),
    user: UserContext = Depends(get_current_user),
):
    """停止正在运行的对话

    设置 cancel_event，后台任务在下一个事件边界停止。
    不更新 stats（用户主动取消）。
    注册表清理由 _run_graph 的 finally 块负责。
    """
    # 归属校验：非本人对话不允许停止
    conv = await ConversationRepo.get_by_id(db, body.conversation_id, user.user_id)
    if not conv:
        return JSONResponse(status_code=404, content=make_conversation_error(ConversationErrorCode.NOT_FOUND))

    task_info = _active_graphs.get(body.conversation_id)
    if task_info:
        task_info.cancel_event.set()
    return JSONResponse({"status": "ok"})
