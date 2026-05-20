from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """应用配置，从环境变量 / .env 文件加载"""

    # 应用基础
    app_name: str = "OctoTutor-API"
    app_version: str = "0.1.0"
    debug: bool = False

    # DashScope
    dashscope_api_key: str = Field(
        ...,
        description="DashScope API Key，用于 Embedding 和 OCR"
    )
    dashscope_embedding_model: str = "text-embedding-v3"
    dashscope_embedding_dimension: int = 768

    # ChromaDB
    chroma_persist_dir: str = "data/chroma_db"

    # 数据目录
    data_raw_dir: str = "data/raw"
    data_parsed_dir: str = "data/parsed"
    data_images_dir: str = "data/images"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
