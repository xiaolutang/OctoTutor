from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """应用配置，从环境变量 / .env 文件加载"""

    # 应用基础
    app_name: str = "OctoTutor-API"
    app_version: str = "0.1.0"
    debug: bool = False

    # DashScope — 用于 OCR 和 Embedding
    dashscope_api_key: str = Field(
        ...,
        description="DashScope API Key，用于 Embedding 和 OCR"
    )
    dashscope_embedding_model: str = "text-embedding-v4"
    dashscope_embedding_dimension: int = 1024

    # JWT 鉴权 — 与 auth-center 共享密钥（HS256）
    auth_jwt_secret: str = Field(
        ...,
        alias="JWT_SECRET_KEY",
        description="JWT 签名密钥，与 auth-center 共享（HS256）",
    )

    # 前端鉴权 SDK 配置 — /api/config 接口返回给前端
    auth_client_id: str = Field(
        default="",
        alias="AUTH_CLIENT_ID",
        description="xlfoundry auth-center 的 OAuth Client ID",
    )
    auth_base_url: str = Field(
        default="",
        alias="AUTH_BASE_URL",
        description="xlfoundry auth-center 的 Base URL",
    )

    # NewAPI (本地 Docker, OpenAI 兼容协议) — 用于 LLM 调用
    newapi_api_key: str = Field(
        default="",
        description="NewAPI API Key，用于 LLM 调用（如 block_type 分类）"
    )
    newapi_base_url: str = "http://localhost:13000/v1"
    llm_model: str = "glm-5.1"

    # PostgreSQL — LangGraph PostgresSaver 持久化
    database_url: str = Field(
        default="postgresql://localhost:5432/octotutor_checkpoints",
        description="PostgreSQL 连接串，用于 LangGraph PostgresSaver",
    )

    # ChromaDB
    chroma_persist_dir: str = "data/chroma_db"

    # 数据目录
    data_raw_dir: str = "data/raw"
    data_parsed_dir: str = "data/parsed"
    data_images_dir: str = "data/images"

    # R019: 图片识别配置
    vision_model: str = "qwen3-vl-flash"
    image_max_size_mb: int = 10           # 单张图片大小上限
    image_max_storage_mb: int = 1000      # uploads 目录高水位（MB），低水位 = 80%

    # R004: Reranker 配置
    rerank_top_n: int = 3
    rerank_model: str = "gte-rerank"
    chat_max_context_tokens: int = 3000

    # R010: Context 相关性阈值（reranker score）
    relevance_threshold: float = 0.50

    # R004: BM25 + RRF 配置
    bm25_enabled: bool = True
    rrf_k: int = 60
    retrieval_top_k: int = 20
    similarity_threshold: float = 0.70

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
