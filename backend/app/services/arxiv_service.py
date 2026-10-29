"""arXiv 检索服务"""
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from app.config import settings


def search_arxiv(query: str, max_results: int = 10) -> list:
    """
    调 arXiv API 搜索论文
    返回 [{title, authors, summary, arxiv_id, pdf_url, updated}]
    """
    params = urllib.parse.urlencode({
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "relevance",
        "sortOrder": "descending",
    })
    url = f"{settings.ARXIV_API_URL}?{params}"

    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = resp.read().decode("utf-8")
    except Exception as e:
        return [{"error": f"arXiv API 调用失败: {e}"}]

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(data)

    papers = []
    for entry in root.findall("atom:entry", ns):
        title = entry.findtext("atom:title", "", ns).strip()
        summary = entry.findtext("atom:summary", "", ns).strip()
        updated = entry.findtext("atom:updated", "", ns)

        authors = [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)]

        arxiv_id = entry.findtext("atom:id", "", ns).split("/abs/")[-1]
        pdf_link = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        for link in entry.findall("atom:link", ns):
            if link.get("title") == "pdf":
                pdf_link = link.get("href", pdf_link)
                break

        papers.append({
            "arxiv_id": arxiv_id,
            "title": title,
            "authors": authors,
            "summary": summary[:300] + "...",
            "updated": updated,
            "pdf_url": pdf_link,
        })

    return papers


def get_daily_papers() -> list:
    """获取 arXiv 最新论文列表"""
    return search_arxiv("artificial intelligence OR machine learning OR RAG OR agent", max_results=20)
