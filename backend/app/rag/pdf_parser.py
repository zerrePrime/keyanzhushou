"""PDF 解析 - PyMuPDF 提取结构化内容 + 切块 + 版式标题树"""
import fitz
import hashlib
import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class ParsedPaper:
    paper_id: str
    title: str = ""
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    chunks: List[dict] = field(default_factory=list)  # [{text, page}]
    references: List[str] = field(default_factory=list)
    total_pages: int = 0
    file_hash: str = ""


def compute_file_hash(filepath: str) -> str:
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_pdf(filepath: str) -> ParsedPaper:
    doc = fitz.open(filepath)
    file_hash = compute_file_hash(filepath)
    paper_id = file_hash[:12]

    paper = ParsedPaper(
        paper_id=paper_id,
        total_pages=doc.page_count,
        file_hash=file_hash,
    )

    # 首页尝试标题/作者
    if doc.page_count > 0:
        first_page = doc[0]
        text_blocks = first_page.get_text("dict")["blocks"]
        for block in text_blocks:
            if block["type"] == 0:
                for line in block["lines"]:
                    for span in line["spans"]:
                        sz, txt = span["size"], span["text"].strip()
                        if not txt:
                            continue
                        if sz >= 14 and not paper.title:
                            paper.title = txt
                        elif paper.title and not paper.authors:
                            paper.authors = [txt]

    # 全文切块（滑窗）
    CHUNK = 800
    OVERLAP = 100
    all_text = ""
    page_map = []

    for pn, page in enumerate(doc):
        t = page.get_text("text").strip()
        if not t:
            continue
        for c in t:
            all_text += c
            page_map.append(pn)

    start = 0
    while start < len(all_text):
        end = min(start + CHUNK, len(all_text))
        chunk_text = all_text[start:end].strip()
        if chunk_text:
            pages = page_map[start:end]
            majority = max(set(pages), key=pages.count)
            paper.chunks.append({"text": chunk_text, "page": majority})
        start += CHUNK - OVERLAP

    # 参考文献
    for pn, page in enumerate(doc):
        text = page.get_text("text")
        if "references" in text.lower() or "bibliography" in text.lower():
            for line in text.split("\n"):
                line = line.strip()
                if line and (line[0].isdigit() or line.startswith("[")) and len(line) > 10:
                    paper.references.append(line[:200])
            break

    doc.close()
    return paper


_PAGE_NO_RE = re.compile(r"^[\d\s\-–—./|]+$")
_NOISE_WORDS = ("attribution", "permission", "copyright", "all rights reserved", "arxiv:", "https://", "http://")


def _is_heading_text(txt: str) -> bool:
    """过滤掉页码、长句、邮箱地址、版权声明等非标题片段"""
    if not (2 <= len(txt) <= 120):
        return False
    if _PAGE_NO_RE.match(txt):
        return False
    if not any(c.isalpha() for c in txt):
        return False
    if "@" in txt:
        return False
    low = txt.lower()
    if any(w in low for w in _NOISE_WORDS):
        return False
    if txt.endswith((",", ";", "，", "；")):
        return False
    if txt.endswith(".") and len(txt) > 60:
        return False
    return True


def extract_outline(filepath: str, max_items: int = 200) -> List[dict]:
    """
    基于版式（字号 + 粗体）提取 PDF 标题树。
    以「行」为单位聚合，跳过旋转水印、版权声明、作者/邮箱区，减少噪声。
    只做实时解析，不写入向量库 metadata，因此不影响已构建的 Chroma 库。
    """
    doc = fitz.open(filepath)
    try:
        lines = []          # (page, size, is_bold, y, text)
        size_weight = {}    # 字号 -> 字符数，用于推断正文字号

        for pn, page in enumerate(doc):
            for block in page.get_text("dict")["blocks"]:
                if block["type"] != 0:
                    continue
                for line in block["lines"]:
                    dx, dy = line.get("dir", (1, 0))
                    if abs(dx - 1) > 0.05 or abs(dy) > 0.05:
                        continue  # 跳过旋转文本（水印、竖排页眉）
                    spans = [s for s in line["spans"] if s["text"].strip()]
                    if not spans:
                        continue
                    txt = "".join(s["text"] for s in spans).strip()
                    size = round(max(float(s["size"]) for s in spans), 1)
                    bold = all(s["flags"] & 16 for s in spans)
                    y = round(min(s["bbox"][1] for s in spans), 1)
                    lines.append((pn, size, bold, y, txt))
                    size_weight[size] = size_weight.get(size, 0) + len(txt)

        if not lines:
            return []

        body_size = max(size_weight, key=size_weight.get)

        # 首页标题上方的页眉/版权声明 + 下方的作者/单位区：字号小于主标题的一律不当标题
        title_y, title_size = None, 0.0
        page0 = [ln for ln in lines if ln[0] == 0 and _is_heading_text(ln[4])]
        if page0:
            _, title_size, _, title_y, _ = max(page0, key=lambda ln: ln[1])

        items, seen = [], set()
        for pn, size, bold, y, txt in lines:
            if not _is_heading_text(txt):
                continue
            if pn == 0 and title_y is not None and y <= title_y + 220 and size < title_size:
                continue

            ratio = size / body_size if body_size else 1.0
            if ratio >= 1.45:
                level = 1
            elif ratio >= 1.20:
                level = 2
            elif ratio >= 1.08:
                level = 3
            elif bold and ratio >= 0.95 and len(txt) <= 60 and "." not in txt and "," not in txt:
                level = 3  # 粗体短行兜底，识别无字号差异的小节标题
            else:
                continue

            key = (pn, txt)
            if key in seen:
                continue
            seen.add(key)
            items.append({"level": level, "title": txt, "page": pn + 1})

        # 兜底：一个标题都没抽到时，用首页最大字号文本作为一级标题
        if not items:
            pn, size, _, _, txt = max(lines, key=lambda s: s[1])
            if _is_heading_text(txt):
                items.append({"level": 1, "title": txt, "page": pn + 1})

        return items[:max_items]
    finally:
        doc.close()


def extract_page_text(filepath: str, page_num: int) -> str:
    """取单页纯文本（1-based 页码），用于逐页翻译"""
    doc = fitz.open(filepath)
    try:
        if page_num < 1 or page_num > doc.page_count:
            return ""
        return doc[page_num - 1].get_text("text").strip()
    finally:
        doc.close()


def chunks_for_rag(paper: ParsedPaper) -> tuple:
    """转 Chroma 格式: (documents, metadatas, ids)"""
    docs, metas, ids = [], [], []
    refs_str = "||".join(paper.references[:50])  # 最多存 50 条引用
    for i, c in enumerate(paper.chunks):
        docs.append(c["text"])
        metas.append({
            "paper_id": paper.paper_id,
            "title": paper.title[:200],
            "page": c["page"],
            "source": f"{paper.paper_id}#p{c['page']}",
            "has_references": "1" if refs_str else "0",
            "references": refs_str,
        })
        ids.append(f"{paper.paper_id}_chunk_{i}")
    return docs, metas, ids
