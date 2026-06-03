"""测试 stream_router.py 的图执行解耦功能

TDD 方法：先写测试，再实现功能。

测试覆盖：
1. _run_graph 正常完成 — DONE sentinel + stats 更新 + 标题生成 + 注册表清理
2. _run_graph 异常 — ERROR sentinel + stats 不更新 + 注册表清理
3. _run_graph 被取消 — break + stats 不更新 + 注册表清理
4. _run_graph 超时 — ERROR sentinel + 注册表清理
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.chat.stream_router import _run_graph
from app.middleware.auth import UserContext


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def _cleanup_active_graphs():
    """每个测试前后清理 _active_graphs，防止测试间泄漏"""
    from app.chat.stream_router import _active_graphs
    _active_graphs.clear()
    yield
    _active_graphs.clear()

@pytest.fixture
def mock_user():
    """Mock 用户上下文"""
    return UserContext(user_id="test-user-123", username="testuser")


@pytest.fixture
def mock_db():
    """Mock 数据库 session"""
    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()
    return db


@pytest.fixture
def mock_graph():
    """Mock graph"""
    return AsyncMock()


@pytest.fixture
def mock_app_state():
    """Mock app.state"""
    state = MagicMock()
    state.generator = AsyncMock()
    state.generator.generate_title = AsyncMock(return_value="测试标题")
    return state


def _make_empty_astream():
    """创建一个立即结束的 mock astream（无事件）"""
    async def mock_astream(*args, **kwargs):
        return
        yield  # 使其成为异步生成器
    return mock_astream


def _register_graph(conversation_id: str) -> tuple[asyncio.Queue, asyncio.Event]:
    """注册一个测试用的 graph 到 _active_graphs"""
    from app.chat.stream_router import _active_graphs, GraphTaskInfo

    queue = asyncio.Queue()
    cancel_event = asyncio.Event()
    task_info = GraphTaskInfo(queue=queue, cancel_event=cancel_event, task=None)
    _active_graphs[conversation_id] = task_info
    return queue, cancel_event


async def _drain_queue_async(queue: asyncio.Queue) -> list:
    """排空队列，返回所有元素（异步版本）"""
    items = []
    while not queue.empty():
        items.append(await queue.get())
    return items


# ============================================================================
# 测试 _run_graph 正常完成
# ============================================================================

@pytest.mark.asyncio
async def test_run_graph_normal_completion_puts_done(
    mock_graph,
    mock_db,
    mock_user,
    mock_app_state,
):
    """正常完成时 queue 收到事件 + DONE sentinel"""
    from app.chat.stream_router import _active_graphs, _GRAPH_DONE

    conversation_id = "conv-normal"
    queue, cancel_event = _register_graph(conversation_id)

    # Mock graph.astream 产生两个事件
    async def mock_astream(*args, **kwargs):
        yield ("updates", {"retrieve": {"sources": []}})
        yield ("messages", (MagicMock(content="token"), {"langgraph_node": "respond"}))

    mock_graph.astream = mock_astream

    with patch("app.chat.stream_router.ConversationRepo.update_message_stats", new_callable=AsyncMock):
        await _run_graph(
            graph=mock_graph, input_state={}, config={},
            queue=queue, cancel_event=cancel_event,
            db=mock_db, conversation_id=conversation_id,
            user=mock_user, question="测试问题",
            is_new=False, app_state=mock_app_state,
        )

    events = await _drain_queue_async(queue)
    assert len(events) == 3  # 两个事件 + DONE
    assert events[-1] is _GRAPH_DONE

    # 注册表已清理
    assert conversation_id not in _active_graphs


@pytest.mark.asyncio
async def test_run_graph_normal_calls_update_stats(
    mock_graph,
    mock_db,
    mock_user,
    mock_app_state,
):
    """正常完成时 update_message_stats 被调用"""
    conversation_id = "conv-stats"
    queue, cancel_event = _register_graph(conversation_id)
    mock_graph.astream = _make_empty_astream()

    with patch("app.chat.stream_router.ConversationRepo.update_message_stats", new_callable=AsyncMock) as mock_stats:
        await _run_graph(
            graph=mock_graph, input_state={}, config={},
            queue=queue, cancel_event=cancel_event,
            db=mock_db, conversation_id=conversation_id,
            user=mock_user, question="测试问题",
            is_new=False, app_state=mock_app_state,
        )

        mock_stats.assert_called_once_with(mock_db, conversation_id)
        mock_db.commit.assert_called()


@pytest.mark.asyncio
async def test_run_graph_normal_generates_title_for_new_conversation(
    mock_graph,
    mock_db,
    mock_user,
    mock_app_state,
):
    """新对话正常完成时标题生成被调用"""
    conversation_id = "conv-title"
    queue, cancel_event = _register_graph(conversation_id)
    mock_graph.astream = _make_empty_astream()

    with patch("app.chat.stream_router.ConversationRepo.update_message_stats", new_callable=AsyncMock):
        with patch("app.chat.stream_router.ConversationRepo.update", new_callable=AsyncMock) as mock_update:
            await _run_graph(
                graph=mock_graph, input_state={}, config={},
                queue=queue, cancel_event=cancel_event,
                db=mock_db, conversation_id=conversation_id,
                user=mock_user, question="测试问题",
                is_new=True, app_state=mock_app_state,
            )

            # 验证 ConversationRepo.update 被调用（标题更新）
            mock_update.assert_called_once()
            call_args = mock_update.call_args
            assert call_args[0][0] == mock_db
            assert call_args[0][1] == conversation_id
            assert call_args[0][2] == mock_user.user_id
            assert call_args[1]["title"] == "测试标题"


@pytest.mark.asyncio
async def test_run_graph_normal_no_title_for_existing_conversation(
    mock_graph,
    mock_db,
    mock_user,
    mock_app_state,
):
    """已有对话正常完成时不生成标题"""
    conversation_id = "conv-no-title"
    queue, cancel_event = _register_graph(conversation_id)
    mock_graph.astream = _make_empty_astream()

    with patch("app.chat.stream_router.ConversationRepo.update_message_stats", new_callable=AsyncMock):
        with patch("app.chat.stream_router.ConversationRepo.update", new_callable=AsyncMock) as mock_update:
            await _run_graph(
                graph=mock_graph, input_state={}, config={},
                queue=queue, cancel_event=cancel_event,
                db=mock_db, conversation_id=conversation_id,
                user=mock_user, question="测试问题",
                is_new=False, app_state=mock_app_state,
            )

            # 已有对话不生成标题
            mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_run_graph_cleans_registry_on_normal_completion(
    mock_graph,
    mock_db,
    mock_user,
    mock_app_state,
):
    """正常完成后 _active_graphs 注册表被清理"""
    from app.chat.stream_router import _active_graphs

    conversation_id = "conv-cleanup"
    queue, cancel_event = _register_graph(conversation_id)
    mock_graph.astream = _make_empty_astream()

    assert conversation_id in _active_graphs  # 注册前确认

    with patch("app.chat.stream_router.ConversationRepo.update_message_stats", new_callable=AsyncMock):
        await _run_graph(
            graph=mock_graph, input_state={}, config={},
            queue=queue, cancel_event=cancel_event,
            db=mock_db, conversation_id=conversation_id,
            user=mock_user, question="测试问题",
            is_new=False, app_state=mock_app_state,
        )

    assert conversation_id not in _active_graphs


# ============================================================================
# 测试 _run_graph 异常
# ============================================================================

@pytest.mark.asyncio
async def test_run_graph_exception_puts_error(
    mock_graph,
    mock_db,
    mock_user,
    mock_app_state,
):
    """graph.astream 抛异常时 queue 收到 ERROR sentinel"""
    from app.chat.stream_router import _active_graphs, _GRAPH_ERROR

    conversation_id = "conv-error"
    queue, cancel_event = _register_graph(conversation_id)

    async def mock_astream_error(*args, **kwargs):
        raise ValueError("Graph execution failed")
        yield  # 使其成为异步生成器

    mock_graph.astream = mock_astream_error

    with patch("app.chat.stream_router.ConversationRepo.update_message_stats", new_callable=AsyncMock) as mock_stats:
        await _run_graph(
            graph=mock_graph, input_state={}, config={},
            queue=queue, cancel_event=cancel_event,
            db=mock_db, conversation_id=conversation_id,
            user=mock_user, question="测试问题",
            is_new=False, app_state=mock_app_state,
        )

    events = await _drain_queue_async(queue)
    assert len(events) == 1
    assert events[0] is _GRAPH_ERROR

    # stats 不更新
    mock_stats.assert_not_called()

    # 注册表被清理
    assert conversation_id not in _active_graphs


# ============================================================================
# 测试 _run_graph 被取消
# ============================================================================

@pytest.mark.asyncio
async def test_run_graph_cancelled_no_sentinel(
    mock_graph,
    mock_db,
    mock_user,
    mock_app_state,
):
    """取消时不放 DONE 或 ERROR sentinel"""
    from app.chat.stream_router import _active_graphs, _GRAPH_DONE, _GRAPH_ERROR

    conversation_id = "conv-cancel"
    queue, cancel_event = _register_graph(conversation_id)

    # 预先设置 cancel_event
    cancel_event.set()

    # Mock astream 产生事件（但循环不会处理，因为 cancel 已设置）
    async def mock_astream_cancel(*args, **kwargs):
        yield ("updates", {"retrieve": {"sources": []}})

    mock_graph.astream = mock_astream_cancel

    with patch("app.chat.stream_router.ConversationRepo.update_message_stats", new_callable=AsyncMock) as mock_stats:
        await _run_graph(
            graph=mock_graph, input_state={}, config={},
            queue=queue, cancel_event=cancel_event,
            db=mock_db, conversation_id=conversation_id,
            user=mock_user, question="测试问题",
            is_new=False, app_state=mock_app_state,
        )

    events = await _drain_queue_async(queue)

    # 没有 DONE 或 ERROR
    assert _GRAPH_DONE not in events
    assert _GRAPH_ERROR not in events
    # 第一个事件前就 break，所以也没有普通事件
    assert len(events) == 0

    # stats 不更新
    mock_stats.assert_not_called()

    # 注册表被清理
    assert conversation_id not in _active_graphs


@pytest.mark.asyncio
async def test_run_graph_cancelled_after_some_events(
    mock_graph,
    mock_db,
    mock_user,
    mock_app_state,
):
    """取消前已放入一些事件，取消后不再放入"""
    from app.chat.stream_router import _active_graphs, _GRAPH_DONE, _GRAPH_ERROR

    conversation_id = "conv-cancel-mid"
    queue, cancel_event = _register_graph(conversation_id)

    # Mock astream：第一个事件后设置 cancel
    async def mock_astream_cancel_mid(*args, **kwargs):
        yield ("updates", {"retrieve": {"sources": []}})
        cancel_event.set()  # 在第二个事件前取消
        await asyncio.sleep(0)
        yield ("updates", {"respond": {}})

    mock_graph.astream = mock_astream_cancel_mid

    with patch("app.chat.stream_router.ConversationRepo.update_message_stats", new_callable=AsyncMock) as mock_stats:
        await _run_graph(
            graph=mock_graph, input_state={}, config={},
            queue=queue, cancel_event=cancel_event,
            db=mock_db, conversation_id=conversation_id,
            user=mock_user, question="测试问题",
            is_new=False, app_state=mock_app_state,
        )

    events = await _drain_queue_async(queue)

    # 第一个事件已放入（在 cancel_event 被设置之前的事件循环迭代中）
    # 注意：取决于实现中 cancel_event.is_set() 检查位置
    # 在当前实现中，检查在 queue.put 之前，所以：
    # 迭代1：cancel 未 set → put 事件1 → cancel 被设置
    # 迭代2：cancel 已 set → break
    assert _GRAPH_DONE not in events
    assert _GRAPH_ERROR not in events

    # stats 不更新
    mock_stats.assert_not_called()

    # 注册表被清理
    assert conversation_id not in _active_graphs


# ============================================================================
# 测试 _run_graph 超时
# ============================================================================

@pytest.mark.asyncio
async def test_run_graph_timeout_puts_error_and_cleans_registry(
    mock_graph,
    mock_db,
    mock_user,
    mock_app_state,
):
    """超时时 queue 收到 ERROR sentinel + stats 不更新 + 注册表被清理"""
    from app.chat.stream_router import _active_graphs, _GRAPH_ERROR

    conversation_id = "conv-timeout"
    queue, cancel_event = _register_graph(conversation_id)

    # Mock graph.astream 抛出 TimeoutError（模拟 asyncio.timeout 触发）
    async def mock_astream_timeout(*args, **kwargs):
        raise TimeoutError()
        yield  # 使其成为异步生成器

    mock_graph.astream = mock_astream_timeout

    with patch("app.chat.stream_router.ConversationRepo.update_message_stats", new_callable=AsyncMock) as mock_stats:
        await _run_graph(
            graph=mock_graph, input_state={}, config={},
            queue=queue, cancel_event=cancel_event,
            db=mock_db, conversation_id=conversation_id,
            user=mock_user, question="测试问题",
            is_new=False, app_state=mock_app_state,
        )

    events = await _drain_queue_async(queue)
    assert len(events) == 1
    assert events[0] is _GRAPH_ERROR

    # 超时不更新 stats
    mock_stats.assert_not_called()

    # 注册表被清理
    assert conversation_id not in _active_graphs


# ============================================================================
# 测试 resume_stream 端点 (R012-BB002)
# ============================================================================

@pytest.mark.asyncio
async def test_resume_stream_task_running_returns_sse(
    mock_user,
    mock_db,
):
    """后台任务运行中 -> 返回 SSE 流（剩余事件）"""
    from app.chat.stream_router import (
        _active_graphs, GraphTaskInfo, _GRAPH_DONE,
    )

    conversation_id = "conv-resume-running"

    # 注册活跃任务
    queue = asyncio.Queue()
    cancel_event = asyncio.Event()
    task_info = GraphTaskInfo(queue=queue, cancel_event=cancel_event, task=None)
    _active_graphs[conversation_id] = task_info

    # 放入一个事件 + DONE
    await queue.put(("updates", {"retrieve": {"sources": []}}))
    await queue.put(_GRAPH_DONE)

    with patch("app.chat.stream_router.ConversationRepo.get_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MagicMock()  # 归属校验通过

        from app.chat.stream_router import resume_stream

        http_request = AsyncMock()
        http_request.is_disconnected = AsyncMock(return_value=False)

        response = await resume_stream(
            conversation_id=conversation_id,
            http_request=http_request,
            checkpointer=AsyncMock(),
            db=mock_db,
            user=mock_user,
        )

    # 应该是 StreamingResponse
    from starlette.responses import StreamingResponse as SR
    assert isinstance(response, SR)

    # 清理
    _active_graphs.pop(conversation_id, None)


@pytest.mark.asyncio
async def test_resume_stream_task_completed_returns_json(
    mock_user,
    mock_db,
):
    """后台任务已完成 -> 返回 JSON（完整消息）"""
    from app.chat.stream_router import _active_graphs
    from starlette.responses import JSONResponse

    conversation_id = "conv-resume-done"

    # 确保注册表中没有该任务
    _active_graphs.pop(conversation_id, None)

    mock_checkpointer = AsyncMock()

    with patch("app.chat.stream_router.ConversationRepo.get_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MagicMock()  # 归属校验通过

        with patch("app.chat.stream_router._load_conversation_by_id", new_callable=AsyncMock) as mock_load:
            from langchain_core.messages import AIMessage
            mock_load.return_value = [
                AIMessage(content="测试回答"),
            ]

            from app.chat.stream_router import resume_stream

            response = await resume_stream(
                conversation_id=conversation_id,
                http_request=AsyncMock(),
                checkpointer=mock_checkpointer,
                db=mock_db,
                user=mock_user,
            )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 200

    # 清理
    _active_graphs.pop(conversation_id, None)


@pytest.mark.asyncio
async def test_resume_stream_no_conversation_returns_404(
    mock_user,
    mock_db,
):
    """非本人对话 -> 返回 404"""
    from app.chat.stream_router import _active_graphs
    from starlette.responses import JSONResponse

    conversation_id = "conv-resume-notfound"
    _active_graphs.pop(conversation_id, None)

    with patch("app.chat.stream_router.ConversationRepo.get_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None  # 归属校验失败

        from app.chat.stream_router import resume_stream

        response = await resume_stream(
            conversation_id=conversation_id,
            http_request=AsyncMock(),
            checkpointer=AsyncMock(),
            db=mock_db,
            user=mock_user,
        )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_resume_stream_completed_no_messages_returns_204(
    mock_user,
    mock_db,
):
    """后台任务已完成但无消息 -> 返回 204"""
    from app.chat.stream_router import _active_graphs
    from starlette.responses import Response

    conversation_id = "conv-resume-empty"
    _active_graphs.pop(conversation_id, None)

    with patch("app.chat.stream_router.ConversationRepo.get_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MagicMock()  # 归属校验通过

        with patch("app.chat.stream_router._load_conversation_by_id", new_callable=AsyncMock) as mock_load:
            mock_load.return_value = []  # 无消息

            from app.chat.stream_router import resume_stream

            response = await resume_stream(
                conversation_id=conversation_id,
                http_request=AsyncMock(),
                checkpointer=AsyncMock(),
                db=mock_db,
                user=mock_user,
            )

    assert isinstance(response, Response)
    assert response.status_code == 204


# ============================================================================
# 测试 stop_chat 端点 (R012-BB003)
# ============================================================================

@pytest.mark.asyncio
async def test_stop_chat_sets_cancel_event():
    """stop_chat 设置 cancel_event"""
    from app.chat.stream_router import _active_graphs, GraphTaskInfo

    conversation_id = "conv-stop-active"
    queue = asyncio.Queue()
    cancel_event = asyncio.Event()
    task_info = GraphTaskInfo(queue=queue, cancel_event=cancel_event, task=None)
    _active_graphs[conversation_id] = task_info

    assert not cancel_event.is_set()

    from app.chat.stream_router import stop_chat
    from app.chat.schemas import StopRequest

    body = StopRequest(conversation_id=conversation_id)
    mock_db = AsyncMock(spec=AsyncSession)
    with patch("app.chat.stream_router.ConversationRepo.get_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MagicMock()  # 归属校验通过
        response = await stop_chat(body=body, db=mock_db, user=UserContext(user_id="test-user-123", username="testuser"))

    assert cancel_event.is_set()

    from starlette.responses import JSONResponse
    assert isinstance(response, JSONResponse)
    assert response.status_code == 200

    # 清理
    _active_graphs.pop(conversation_id, None)


@pytest.mark.asyncio
async def test_stop_chat_nonexistent_conversation_returns_404():
    """stop_chat 对非本人对话返回 404"""
    from app.chat.stream_router import _active_graphs, stop_chat
    from app.chat.schemas import StopRequest

    conversation_id = "conv-stop-nonexist"
    _active_graphs.pop(conversation_id, None)

    body = StopRequest(conversation_id=conversation_id)
    mock_db = AsyncMock(spec=AsyncSession)
    with patch("app.chat.stream_router.ConversationRepo.get_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None  # 归属校验失败
        response = await stop_chat(body=body, db=mock_db, user=UserContext(user_id="test-user-123", username="testuser"))

    from starlette.responses import JSONResponse
    assert isinstance(response, JSONResponse)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_stop_chat_cancelled_task_cleans_registry(
    mock_graph,
    mock_db,
    mock_user,
    mock_app_state,
):
    """stop 设置 cancel_event 后，后台任务停止并清理注册表"""
    from app.chat.stream_router import _active_graphs, _GRAPH_DONE, _GRAPH_ERROR

    conversation_id = "conv-stop-cleanup"
    queue, cancel_event = _register_graph(conversation_id)

    # Mock astream 产生事件后等待 cancel，然后 yield 下一个事件（将被 cancel 拦截）
    async def mock_astream_slow(*args, **kwargs):
        yield ("updates", {"retrieve": {"sources": []}})
        # 等待 cancel 被设置
        for _ in range(20):
            await asyncio.sleep(0.05)
            if cancel_event.is_set():
                break
        # cancel 已设置，下一个事件将在 _run_graph 中被拦截
        yield ("updates", {"respond": {}})

    mock_graph.astream = mock_astream_slow

    with patch("app.chat.stream_router.ConversationRepo.update_message_stats", new_callable=AsyncMock):
        # 启动后台任务
        task = asyncio.create_task(
            _run_graph(
                graph=mock_graph, input_state={}, config={},
                queue=queue, cancel_event=cancel_event,
                db=mock_db, conversation_id=conversation_id,
                user=mock_user, question="测试问题",
                is_new=False, app_state=mock_app_state,
            )
        )

        # 等一会儿让第一个事件进入 queue
        await asyncio.sleep(0.05)

        # 设置 cancel
        cancel_event.set()

        # 等待后台任务完成
        await task

    # 注册表被清理
    assert conversation_id not in _active_graphs

    # 没有 DONE 或 ERROR（用户取消不放入 sentinel）
    events = await _drain_queue_async(queue)
    assert _GRAPH_DONE not in events
    assert _GRAPH_ERROR not in events
