"""arXiv 检索路由"""
import os
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.services.arxiv_service import search_arxiv, get_daily_papers
from app.services.paper_service import upload_paper

router = APIRouter(prefix="/api/arxiv", tags=["arxiv"])


class SearchReq(BaseModel):
    query: str
    max_results: int = 10


class DownloadReq(BaseModel):
    url: str
    filename: str = ""


@router.post("/search")
async def search(req: SearchReq):
    return {"papers": search_arxiv(req.query, req.max_results)}


@router.get("/daily")
async def daily():
    return get_daily_papers()


@router.post("/download")
async def download(req: DownloadReq):
    """下载 arXiv PDF → 解析 → 去重检测 → 入库"""
    parsed = urllib.parse.urlparse(req.url)
    if parsed.scheme not in ("http", "https") or not (parsed.hostname or "").endswith("arxiv.org"):
        raise HTTPException(status_code=400, detail="只支持 arXiv 的 PDF 链接")

    name = Path(req.filename).name or Path(parsed.path).name or "paper.pdf"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    tmp_path = None
    try:
        with urllib.request.urlopen(req.url, timeout=60) as resp:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp_path = tmp.name
                written = 0
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail=f"PDF 超过 {settings.MAX_UPLOAD_SIZE_MB}MB 限制",
                        )
                    tmp.write(chunk)
        return upload_paper(tmp_path, name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"下载失败: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
