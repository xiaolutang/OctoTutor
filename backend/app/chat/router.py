from fastapi import APIRouter, Depends, HTTPException

from app.chat.schemas import ChatRequest, ChatResponse
from app.chat.service import ChatService
from app.chat.dependencies import get_chat_service

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, service: ChatService = Depends(get_chat_service)):
    result = service.handle_chat(request.question, request.top_k)
    if result is None:
        raise HTTPException(status_code=404, detail="未找到相关教材内容")
    return result
