"""全局配置"""
from pydantic_settings import BaseSettings
from pathlib import Path

# 项目根目录 (backend/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    APP_NAME: str = "Research Assistant Agent"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    # ===== LLM Provider 切换 =====
    # ollama = 本地模型（开发/有 GPU 的服务器）
    # openai_compatible = 云端 OpenAI 兼容 API（百炼 / 硅基流动 / DeepSeek 通用）
    LLM_PROVIDER: str = "ollama"

    # Ollama 本地 LLM
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_LLM_MODEL: str = "qwen2.5:7b"
    OLLAMA_CODE_MODEL: str = "qwen2.5-coder:7b"

    # OpenAI 兼容云 API
    OPENAI_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "qwen-plus"

    LLM_TEMPERATURE: float = 0.5
    LLM_MAX_TOKENS: int = 1024
    LLM_TIMEOUT: int = 120

    # Embedding: 用 Chroma 内置 ONNX MiniLM，无需联网下载
    EMBEDDING_PROVIDER: str = "onnx_mini_lm"  # onnx_mini_lm | ollama

    # Chroma 向量库 (用 TRAE 允许写入的 d:\vue 路径，避免沙盒拦截 journal 文件)
    CHROMA_PERSIST_DIR: str = r"d:\vue\chroma_db"
    CHROMA_COLLECTION_NAME: str = "research_papers"

    # 文件 (也用 d:\vue 路径，避开沙盒)
    UPLOAD_DIR: str = r"d:\vue\uploads"
    MAX_UPLOAD_SIZE_MB: int = 100

    # arXiv
    ARXIV_API_URL: str = "http://export.arxiv.org/api/query"

    # 端口
    BACKEND_PORT: int = 8000
    FRONTEND_PORT: int = 5173

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
Path(settings.CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
