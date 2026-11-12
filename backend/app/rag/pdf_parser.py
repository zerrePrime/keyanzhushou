"""PDF 解析 - PyMuPDF 提取结构化内容 + 切块 + 版式标题树

扫描件（无文本层）自动回退到 Tesseract OCR，
对应官方测试用例 1706.03762v1_img.pdf 的解析路径。
"""
import fitz
import hashlib
import io
import os
import re
from dataclasses import dataclass, field
from typing import List

OCR_ENABLED = os.getenv("OCR_ENABLED", "1") == "1"
OCR_MAX_PAGES = int(os.getenv("OCR_MAX_PAGES", "100"))
OCR_DPI = int(os.getenv("OCR_DPI", "200"))
OCR_LANG = os.getenv("OCR_LANG", "eng+chi_sim")
# 每页文本少于此字符数即视为"没有文本层"
OCR_MIN_TEXT_PER_PAGE = 20

# 参考文献条目编号：[1] / 1.
_REF_ITEM_RE = re.compile(r"^(?:\[\d{1,4}\]|\d{1,4}\.)\s")
_REF_YEAR_RE = re.compile(r"(?:19|20)\d{2}")


def _extract_references(text: str) -> List[str]:
    """
    抽出参考文献条目。列表有两种排法：
    带编号（[1] ...）和作者开头的段落式（... In NIPS, 2012.），后者靠条目末尾年份切分。
    """
    entries, cur = [], ""
    for line in text.split("\n"):
        line = " ".join(line.split())
        if not line or len(line) < 3 or line.isdigit():
            continue
        if _REF_ITEM_RE.match(line):
            if cur:
                entries.append(cur[:220])
            cur = line
        else:
            cur = f"{cur} {line}".strip() if cur else line
        # 条目以年份（可带句点）结尾，或已堆得过长，则收一条
        if _REF_YEAR_RE.search(cur[-30:]) and (cur.endswith(".") or len(cur) > 260):
            entries.append(cur[:220])
            cur = ""
        if len(entries) >= 80:
            break
    if cur.strip() and len(entries) < 80:
        entries.append(cur[:220])
    return entries


def _find_reference_start(text: str) -> int:
    """按独立标题行定位参考文献区，返回起始行下标；找不到返回 -1。"""
    lines = text.split("\n")
    start = -1
    for i, ln in enumerate(lines):
        s = ln.strip().lower().rstrip(":.")
        if s in ("references", "bibliography", "reference"):
            start = i
    return start


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


def _ocr_page(page) -> str:
    """把页面渲染成位图再 OCR，用于没有文本层的扫描页"""
    if not OCR_ENABLED:
        return ""
    try:
        import pytesseract
        from PIL import Image

        pix = page.get_pixmap(dpi=OCR_DPI)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        return pytesseract.image_to_string(img, lang=OCR_LANG).strip()
    except Exception:
        return ""


def _detect_scanned(doc) -> bool:
    """抽样前 3 页，全部几乎没有文本 → 判定为扫描件"""
    if not OCR_ENABLED or doc.page_count == 0:
        return False
    sample = min(3, doc.page_count)
    return all(
        len(doc[i].get_text("text").strip()) < OCR_MIN_TEXT_PER_PAGE
        for i in range(sample)
    )


def parse_pdf(filepath: str) -> ParsedPaper:
    doc = fitz.open(filepath)
    file_hash = compute_file_hash(filepath)
    paper_id = file_hash[:12]

    paper = ParsedPaper(
        paper_id=paper_id,
        total_pages=doc.page_count,
        file_hash=file_hash,
    )

    scanned = _detect_scanned(doc)
    ocr_done = 0

    # 首页尝试标题/作者（扫描件走 OCR 文本）
    if doc.page_count > 0:
        first_page = doc[0]
        if scanned:
            first_lines = [
                ln.strip() for ln in _ocr_page(first_page).splitlines() if ln.strip()
            ]
            ocr_done += 1
            # 复用标题过滤规则剔除 arXiv 页眉/版权声明；标题在页面顶部，取最靠前的候选行
            candidates = [ln for ln in first_lines[:8] if _is_heading_text(ln)]
            title = candidates[0][:200] if candidates else (
                first_lines[0][:200] if first_lines else ""
            )
            if title:
                paper.title = title
                pos = first_lines.index(title) if title in first_lines else 0
                if pos + 1 < len(first_lines):
                    paper.authors = [first_lines[pos + 1][:100]]
        else:
            text_blocks = first_page.get_text("dict")["blocks"]
            lines = []
            for block in text_blocks:
                if block["type"] == 0:
                    for line in block["lines"]:
                        spans = [s for s in line["spans"] if s["text"].strip()]
                        if spans:
                            lines.append(
                                (max(float(s["size"]) for s in spans), _join_spans(spans))
                            )
            # 标题常跨多行且字号一致，逐行拼接；作者行字号明显更小才收作者
            title_size = 0.0
            for sz, txt in lines:
                if not paper.title:
                    if sz >= 14:
                        paper.title, title_size = txt, sz
                    continue
                if paper.authors:
                    break
                if sz >= title_size * 0.9:
                    paper.title = f"{paper.title} {txt}"
                else:
                    paper.authors = [txt]

    # 全文切块（滑窗）；扫描件逐页 OCR，正常 PDF 直接取文本层
    CHUNK = 800
    OVERLAP = 100
    parts = []
    page_map = []

    for pn, page in enumerate(doc):
        if scanned and ocr_done <= OCR_MAX_PAGES:
            t = _ocr_page(page)
            ocr_done += 1
        else:
            t = page.get_text("text").strip()
        if not t:
            continue
        seg = t + "\n"
        parts.append(seg)
        page_map.extend([pn] * len(seg))

    all_text = "".join(parts)

    start = 0
    while start < len(all_text):
        end = min(start + CHUNK, len(all_text))
        chunk_text = all_text[start:end].strip()
        if chunk_text:
            pages = page_map[start:end]
            majority = max(set(pages), key=pages.count)
            paper.chunks.append({"text": chunk_text, "page": majority})
        start += CHUNK - OVERLAP

    # 参考文献：以最后一个独立的 References/Bibliography 标题行为准
    # （正文里也可能出现 references 一词，按字符串查找会定位到错误位置）
    lines = all_text.split("\n")
    ref_start = _find_reference_start(all_text)
    if ref_start != -1:
        paper.references = _extract_references("\n".join(lines[ref_start + 1:]))

    doc.close()
    return paper


_PAGE_NO_RE = re.compile(r"^[\d\s\-–—./|]+$")
_NOISE_WORDS = ("attribution", "permission", "copyright", "all rights reserved", "arxiv:", "https://", "http://")


def _join_spans(spans) -> str:
    """按相邻 span 的水平间距拼接文本

    PDF 里的标题常被排版引擎拆成多个 span（甚至逐词），直接 join 会丢空格，
    例如 "UnderstandingDeepLearning"。这里用字宽比例判断词间间隙补回空格。
    """
    out: List[str] = []
    prev_x1 = None
    prev_size = 0.0
    for s in spans:
        text = s["text"]
        if not text:
            continue
        x0 = float(s["bbox"][0])
        size = float(s["size"]) or 1.0
        if out and prev_x1 is not None and not text.startswith(" ") and not out[-1].endswith(" "):
            # 间隙超过约 1/4 个字宽，视为词间空格
            if x0 - prev_x1 > 0.25 * max(prev_size, size):
                out.append(" ")
        out.append(text)
        prev_x1 = float(s["bbox"][2])
        prev_size = size
    return "".join(out).strip()


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
    以「行」为单位聚合，跳过旋转水印、版权声明、作者/邮箱区，
    以及 PDF 自带的目录页（Contents）避免把目录条目误收进标题树。
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
                    txt = _join_spans(spans)
                    size = round(max(float(s["size"]) for s in spans), 1)
                    bold = all(s["flags"] & 16 for s in spans)
                    y = round(min(s["bbox"][1] for s in spans), 1)
                    lines.append((pn, size, bold, y, txt))
                    size_weight[size] = size_weight.get(size, 0) + len(txt)

        if not lines:
            return []

        body_size = max(size_weight, key=size_weight.get)

        # -------- 预检测 PDF 自带的目录页 --------
        # 目录页（Contents/Table of Contents）的特征：
        # 1) 先找到独立的 "Contents" 大字号标题
        # 2) 该页及后续连续若干页，每行末尾跟页码（阿拉伯或罗马）
        # 3) 这些页上 50%+ 的行都是 "标题... 页码" 格式
        toc_pages = set()          # {page_idx, ...}
        _TOC_HEADER_RE = re.compile(r'^(contents|table\s+of\s+contents|目录|目\s*录)$', re.I)
        # 末尾跟页码（阿拉伯数字或小写罗马数字），前面可有省略号/点/空白
        _TRAIL_NUM_RE = re.compile(r'[\s.·\-]{0,6}([0-9ivxlcdm]+)$', re.I)

        # 第一步：找 "Contents" 标题所在页
        toc_starts = set()
        for pn, size, bold, y, txt in lines:
            if _TOC_HEADER_RE.match(txt.strip()) and size / body_size >= 1.0:
                toc_starts.add(pn)

        # 第二步：从每个起始页向右扩展，直到连续两页不再像目录
        for start in sorted(toc_starts):
            p = start
            consecutive_non_toc = 0
            while p < doc.page_count and consecutive_non_toc < 2:
                page_lines = [ln for ln in lines if ln[0] == p]
                if not page_lines:
                    consecutive_non_toc += 1
                    p += 1
                    continue
                trail_num = sum(1 for ln in page_lines if _TRAIL_NUM_RE.search(ln[4].strip()))
                ratio = trail_num / len(page_lines)
                if ratio >= 0.4 and len(page_lines) >= 3:
                    toc_pages.add(p)
                    consecutive_non_toc = 0
                else:
                    consecutive_non_toc += 1
                p += 1

        # -------- 单页标题抽取（跳过目录页） --------
        # 首页标题上方的页眉/版权声明 + 下方的作者/单位区：字号小于主标题的一律不当标题
        title_y, title_size = None, 0.0
        page0 = [ln for ln in lines if ln[0] == 0 and _is_heading_text(ln[4])]
        if page0:
            _, title_size, _, title_y, _ = max(page0, key=lambda ln: ln[1])

        items, seen = [], set()
        for pn, size, bold, y, txt in lines:
            if pn in toc_pages:         # ← 目录页整页跳过
                continue
            if not _is_heading_text(txt):
                continue
            if _TRAIL_NUM_RE.search(txt.strip()) and len(txt.strip()) <= 20:
                continue                 # ← 末尾只有页码的短行（"ix", "15", "Chapter 3 ... p.42"）
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
    """取单页纯文本（1-based 页码），用于逐页翻译；扫描页回退 OCR"""
    doc = fitz.open(filepath)
    try:
        if page_num < 1 or page_num > doc.page_count:
            return ""
        page = doc[page_num - 1]
        text = page.get_text("text").strip()
        if text:
            return text
        return _ocr_page(page)
    finally:
        doc.close()


def chunks_for_rag(paper: ParsedPaper) -> tuple:
    """转 Chroma 格式: (documents, metadatas, ids)"""
    docs, metas, ids = [], [], []
    refs_str = "||".join(paper.references[:80])  # 最多存 80 条引用
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
