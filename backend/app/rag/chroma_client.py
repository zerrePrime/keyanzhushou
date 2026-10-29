"""Chroma 向量库 + ONNX MiniLM Embedding"""
import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2
from app.config import settings


def get_chroma_client():
    return chromadb.PersistentClient(
        path=settings.CHROMA_PERSIST_DIR,
        settings=ChromaSettings(anonymized_telemetry=False),
    )


def get_embedding_function():
    """默认 Chroma 内置 ONNX MiniLM，首次用自动下载约 23MB"""
    return ONNXMiniLM_L6_V2()


def get_collection():
    client = get_chroma_client()
    ef = get_embedding_function()
    return client.get_or_create_collection(
        name=settings.CHROMA_COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )
