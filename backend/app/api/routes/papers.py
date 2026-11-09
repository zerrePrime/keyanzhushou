"""论文管理路由"""
import os
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from app.services.paper_service import upload_paper, list_papers, delete_paper
from app.rag.pdf_parser import extract_outline, extract_page_text
from app.config import settings

router = APIRouter(prefix="/api/papers", tags=["papers"])


def _resolve_pdf(paper_id: str) -> Path:
    """按 paper_id 定位已上传的 PDF，找不到直接抛 404"""
    paper_dir = Path(settings.UPLOAD_DIR) / paper_id
    if not paper_dir.exists():
        raise HTTPException(status_code=404, detail="论文文件不存在")
    pdfs = list(paper_dir.glob("*.pdf"))
    if not pdfs:
        raise HTTPException(status_code=404, detail="PDF 文件丢失")
    return pdfs[0]


@router.post("/upload")
async def upload(file: UploadFile = File(...)):
    import tempfile, os
    suffix = os.path.splitext(file.filename)[1] or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        # 解析与向量化是分钟级阻塞操作，放到线程池避免卡死事件循环
        return await run_in_threadpool(upload_paper, tmp_path, file.filename)
    finally:
        os.unlink(tmp_path)


@router.get("/")
async def get_all():
    return {"papers": list_papers()}


@router.delete("/{paper_id}")
async def delete(paper_id: str):
    return delete_paper(paper_id)


@router.get("/{paper_id}/file")
async def get_file(paper_id: str):
    """获取已上传的 PDF 文件（PDF.js 渲染用）

    paper_id 对应固定文件内容，可放心让浏览器长缓存：
    切回看过的论文时直接从磁盘缓存读取，无需重新下载。
    """
    pdf = _resolve_pdf(paper_id)
    return FileResponse(
        pdf,
        media_type="application/pdf",
        filename=pdf.name,
        content_disposition_type="inline",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/{paper_id}/outline")
async def get_outline(paper_id: str):
    """版式标题树：按字号/粗体实时解析，供阅读器目录导航使用"""
    pdf = _resolve_pdf(paper_id)
    try:
        items = extract_outline(str(pdf))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"标题解析失败: {e}")
    return {"paper_id": paper_id, "total": len(items), "outline": items}


@router.get("/{paper_id}/text")
async def get_page_text(paper_id: str, page: int = 1):
    """取单页纯文本，供逐页翻译使用"""
    pdf = _resolve_pdf(paper_id)
    text = extract_page_text(str(pdf), page)
    return {"paper_id": paper_id, "page": page, "text": text}
