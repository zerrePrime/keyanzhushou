"""arXiv 检索路由"""
import os
import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.services.arxiv_service import search_arxiv, get_daily_papers
from app.services.paper_service import upload_paper

router = APIRouter(prefix="/api/arxiv", tags=["arxiv"])

# 服务器到 arxiv.org 的国际链路单连接实测只有 20KB/s 左右，多连接分片可到 ~65KB/s
DOWNLOAD_CONNECTIONS = max(1, int(os.getenv("ARXIV_DOWNLOAD_CONNECTIONS", "8")))
_UA = {"User-Agent": "Mozilla/5.0"}
_PROBE_BYTES = 256 * 1024


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


def _stream_to_file(resp, dest: str, max_bytes: int) -> int:
    """把响应流写到文件，超过大小上限立刻中止。"""
    written = 0
    with open(dest, "wb") as f:
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
            f.write(chunk)
    return written


def _fetch_range(url: str, start: int, end: int, timeout: int = 120) -> bytes:
    req = urllib.request.Request(
        url, headers={**_UA, "Range": f"bytes={start}-{end}"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _download_pdf(url: str, dest: str, max_bytes: int) -> int:
    """
    下载 PDF 到 dest。

    到 arxiv.org 的国际链路单连接吞吐只有 20KB/s 左右，2MB 的论文要一百多秒。
    这里先发一个 256KB 的 Range 请求，从 Content-Range 拿到文件总大小，
    再把剩余字节切成多段交给多个线程并行拉取（实测 8 连接约 65KB/s）。
    服务端不支持 Range 时退化为单连接流式下载。
    """
    probe = urllib.request.Request(
        url, headers={**_UA, "Range": f"bytes=0-{_PROBE_BYTES - 1}"}
    )
    with urllib.request.urlopen(probe, timeout=120) as resp:
        content_range = resp.headers.get("Content-Range") or ""
        if resp.status != 206 or "/" not in content_range:
            return _stream_to_file(resp, dest, max_bytes)

        total = int(content_range.rsplit("/", 1)[-1])
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"PDF 超过 {settings.MAX_UPLOAD_SIZE_MB}MB 限制",
            )
        head = resp.read()

    if len(head) >= total:
        with open(dest, "wb") as f:
            f.write(head[:total])
        return total

    workers = min(DOWNLOAD_CONNECTIONS, max(1, (total - len(head)) // (128 * 1024)))
    if workers <= 1:
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=300) as resp:
            return _stream_to_file(resp, dest, max_bytes)

    seg = (total - len(head)) // workers
    ranges = []
    for i in range(workers):
        start = len(head) + i * seg
        end = total - 1 if i == workers - 1 else start + seg - 1
        ranges.append((start, end))

    tmp_dir = tempfile.mkdtemp(prefix="arxiv_part_")
    parts = [os.path.join(tmp_dir, f"part{i}") for i in range(workers)]
    errors = []

    def fetch(i: int):
        try:
            data = _fetch_range(url, *ranges[i])
            with open(parts[i], "wb") as f:
                f.write(data)
        except Exception as e:  # 任一分片失败就在合并前整体回退
            errors.append(e)

    threads = [threading.Thread(target=fetch, args=(i,)) for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    if errors:
        for p in parts:
            if os.path.exists(p):
                os.unlink(p)
        os.rmdir(tmp_dir)
        req = urllib.request.Request(url, headers=_UA)
        with urllib.request.urlopen(req, timeout=300) as resp:
            return _stream_to_file(resp, dest, max_bytes)

    written = len(head)
    with open(dest, "wb") as out:
        out.write(head)
        for p in parts:
            with open(p, "rb") as f:
                while True:
                    chunk = f.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    written += len(chunk)
            os.unlink(p)
    os.rmdir(tmp_dir)

    if written > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"PDF 超过 {settings.MAX_UPLOAD_SIZE_MB}MB 限制",
        )
    return written


def _download_and_ingest(url: str, name: str, max_bytes: int):
    """同步下载 + 解析入库。

    下载和解析是分钟级阻塞操作，必须放到线程池执行：
    若直接跑在事件循环里，整个后端（列表、健康检查、问答）都会失去响应。
    """
    tmp_path = None
    try:
        fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        _download_pdf(url, tmp_path, max_bytes)
        return upload_paper(tmp_path, name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"下载失败: {e}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


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
    return await run_in_threadpool(_download_and_ingest, req.url, name, max_bytes)
