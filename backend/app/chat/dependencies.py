from fastapi import Request, Depends

from app.domain.protocols import Reranker, Generator
from app.chat.service import ChatService
from app.config import settings


def get_settings():
    return settings


def get_embedding(request: Request):
    return request.app.state.embedding_service


def get_vector_store(request: Request):
    return request.app.state.vector_store


def get_bm25(request: Request):
    return request.app.state.bm25


def get_reranker(request: Request) -> Reranker:
    return request.app.state.reranker


def get_generator(request: Request) -> Generator:
    return request.app.state.generator


def get_chat_service(
    embedding=Depends(get_embedding),
    vector_store=Depends(get_vector_store),
    bm25=Depends(get_bm25),
    reranker=Depends(get_reranker),
    generator=Depends(get_generator),
    settings=Depends(get_settings),
) -> ChatService:
    return ChatService(embedding, vector_store, bm25, reranker, generator, settings)
