"""ChromaDB VectorStore 封装

定义 VectorStore Protocol 接口（upsert/query/delete），
并提供基于 ChromaDB PersistentClient 的 ChromaDBStore 实现。
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

import chromadb

from app.rag.models import Chunk, ChunkMetadata, QueryResult


@runtime_checkable
class VectorStore(Protocol):
    """向量存储抽象协议

    定义 upsert/query/delete 三个核心操作，
    ChromaDBStore 和未来的 MockStore 都需实现此协议。
    """

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        """批量插入/更新 chunks（含 embedding 向量）

        Args:
            chunks: 分块列表，每个 chunk 包含 chunk_id, text, metadata
            embeddings: 与 chunks 一一对应的 embedding 向量列表
        """
        ...

    def query(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where: dict | None = None,
    ) -> list[QueryResult]:
        """向量相似度查询

        Args:
            query_embedding: 查询向量
            top_k: 返回最相似的 top-K 结果
            where: ChromaDB where 过滤条件（如 {"book": "必修第一册"}）

        Returns:
            按相似度排序的 QueryResult 列表（降序）
        """
        ...

    def delete(self, where: dict) -> None:
        """按 metadata 条件删除

        Args:
            where: ChromaDB where 过滤条件
        """
        ...


class ChromaDBStore:
    """基于 ChromaDB PersistentClient 的 VectorStore 实现

    使用 ChromaDB 嵌入式 PersistentClient 持久化向量数据，
    支持 cosine similarity 查询和 metadata where 过滤。

    Args:
        persist_directory: 持久化目录路径，默认 "data/chroma_db"
        collection_name: collection 名称，默认 "octotutor_chunks"
    """

    def __init__(
        self,
        persist_directory: str | Path = "data/chroma_db",
        collection_name: str = "octotutor_chunks",
    ) -> None:
        self._persist_directory = str(persist_directory)
        self._collection_name = collection_name
        self._client = chromadb.PersistentClient(path=self._persist_directory)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        """批量插入/更新 chunks（含 embedding 向量）

        Args:
            chunks: 分块列表
            embeddings: 与 chunks 一一对应的 embedding 向量列表

        Raises:
            ValueError: chunks 和 embeddings 长度不一致
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"chunks ({len(chunks)}) 和 embeddings ({len(embeddings)}) 长度不一致"
            )

        if not chunks:
            return

        ids = [chunk.chunk_id for chunk in chunks]
        documents = [chunk.text for chunk in chunks]
        metadatas = [chunk.metadata.to_dict() for chunk in chunks]

        self._collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,  # type: ignore[arg-type]
            embeddings=embeddings,
        )

    def query(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where: dict | None = None,
    ) -> list[QueryResult]:
        """向量相似度查询

        Args:
            query_embedding: 查询向量
            top_k: 返回最相似的 top-K 结果
            where: ChromaDB where 过滤条件

        Returns:
            按相似度降序排列的 QueryResult 列表
        """
        query_params: dict = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where is not None:
            query_params["where"] = where  # type: ignore[assignment]

        results = self._collection.query(**query_params)  # type: ignore[arg-type]

        # ChromaDB query 返回格式:
        # ids: list[list[str]]
        # documents: list[list[str]]
        # metadatas: list[list[dict]]
        # distances: list[list[float]]
        if not results["ids"] or not results["ids"][0]:
            return []

        query_results: list[QueryResult] = []
        ids = results["ids"][0]
        documents = results["documents"][0] if results["documents"] else [""] * len(ids)
        metadatas = (
            results["metadatas"][0] if results["metadatas"] else [{}] * len(ids)
        )
        distances = results["distances"][0] if results["distances"] else [0.0] * len(ids)

        for chunk_id, text, meta, distance in zip(ids, documents, metadatas, distances):
            score = 1.0 - distance
            # 解析 source_pages（逗号分隔字符串 → int 列表）
            raw_pages = meta.get("source_pages", "")
            if isinstance(raw_pages, str) and raw_pages.strip():
                source_pages = [int(p.strip()) for p in raw_pages.split(",") if p.strip()]
            elif isinstance(raw_pages, list):
                source_pages = [int(p) for p in raw_pages]
            else:
                source_pages = []
            metadata = ChunkMetadata(
                book=meta.get("book", ""),
                chapter=meta.get("chapter", ""),
                section=meta.get("section", ""),
                section_id=meta.get("section_id", ""),
                page=int(meta.get("page", 0)),
                page_start=int(meta.get("page_start", meta.get("page", 0))),
                page_end=int(meta.get("page_end", meta.get("page", 0))),
                source_pages=source_pages,
                chunk_type=meta.get("chunk_type", ""),
                block_type=meta.get("block_type", "unknown"),
                has_formula=bool(meta.get("has_formula", False)),
                parent_id=meta.get("parent_id", ""),
                child_index=int(meta.get("child_index", 0)),
            )
            query_results.append(
                QueryResult(
                    chunk_id=chunk_id,
                    text=text,
                    metadata=metadata,
                    score=score,
                )
            )

        return query_results

    def delete(self, where: dict) -> None:
        """按 metadata 条件删除

        Args:
            where: ChromaDB where 过滤条件
        """
        self._collection.delete(where=where)

    def get_all_chunks(self) -> list[Chunk]:
        """获取 collection 中的全量 chunks，供 BM25 索引构建使用

        使用 ChromaDB .get() 无过滤条件拉取全部数据，
        返回格式与 .query() 类似但不是嵌套列表。

        Returns:
            collection 中所有 Chunk 对象列表
        """
        results = self._collection.get(
            include=["documents", "metadatas"]
        )

        if not results["ids"]:
            return []

        ids = results["ids"]
        documents = results["documents"] if results["documents"] else [""] * len(ids)
        metadatas = results["metadatas"] if results["metadatas"] else [{}] * len(ids)

        chunks: list[Chunk] = []
        for chunk_id, text, meta in zip(ids, documents, metadatas):
            # 解析 source_pages（与 query 方法保持一致的解析逻辑）
            raw_pages = meta.get("source_pages", "")
            if isinstance(raw_pages, str) and raw_pages.strip():
                source_pages = [int(p.strip()) for p in raw_pages.split(",") if p.strip()]
            elif isinstance(raw_pages, list):
                source_pages = [int(p) for p in raw_pages]
            else:
                source_pages = []
            metadata = ChunkMetadata(
                book=meta.get("book", ""),
                chapter=meta.get("chapter", ""),
                section=meta.get("section", ""),
                section_id=meta.get("section_id", ""),
                page=int(meta.get("page", 0)),
                page_start=int(meta.get("page_start", meta.get("page", 0))),
                page_end=int(meta.get("page_end", meta.get("page", 0))),
                source_pages=source_pages,
                chunk_type=meta.get("chunk_type", ""),
                block_type=meta.get("block_type", "unknown"),
                has_formula=bool(meta.get("has_formula", False)),
                parent_id=meta.get("parent_id", ""),
                child_index=int(meta.get("child_index", 0)),
            )
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    text=text,
                    metadata=metadata,
                )
            )

        return chunks

    def count(self) -> int:
        """返回 collection 中的文档数量"""
        return self._collection.count()
