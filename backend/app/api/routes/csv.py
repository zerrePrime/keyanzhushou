"""CSV 数据可视化路由 - 上传解析 / 图表配置 / 图注 / TikZ·Mermaid 导出"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from app.rag.qa_service import llm_chat
from app.services import csv_service
import pandas as pd
import io

router = APIRouter(prefix="/api/csv", tags=["csv"])


def _read_upload(content: bytes) -> pd.DataFrame:
    """CSV 解码：先 UTF-8，失败回退 GBK（国内 Excel 导出常见）"""
    last = None
    for enc in ("utf-8-sig", "gbk"):
        try:
            return pd.read_csv(io.BytesIO(content), encoding=enc)
        except Exception as e:  # noqa: BLE001
            last = e
    raise HTTPException(400, f"CSV 解析失败：{last}")


@router.post("/upload")
async def upload_csv(file: UploadFile = File(...)):
    """上传 CSV，返回结构画像 + 图表推荐"""
    name = (file.filename or "").lower()
    if not name.endswith((".csv", ".tsv", ".txt")):
        raise HTTPException(400, "目前仅支持 CSV / TSV 文件")

    content = await file.read()
    if not content:
        raise HTTPException(400, "文件内容为空")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件超过 10MB，请先裁剪")

    df = _read_upload(content)
    if df.empty:
        raise HTTPException(400, "CSV 中没有数据行")

    file_id = csv_service.save_csv(content, file.filename)
    result = csv_service.profile(df)
    result.update({"file_id": file_id, "filename": file.filename})
    return result


class ChartReq(BaseModel):
    file_id: str
    chart_type: str = "bar"
    x: str = ""
    series: list[str] = []


@router.post("/chart")
async def build_chart(req: ChartReq):
    """根据列选择生成 ECharts option"""
    try:
        df = csv_service.load_csv(req.file_id)
        option = csv_service.build_option(df, req.chart_type, req.x, req.series)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"option": option, "chart_type": req.chart_type}


@router.post("/caption")
async def gen_caption(req: ChartReq):
    """基于真实数据统计生成学术规范 Figure Caption"""
    try:
        df = csv_service.load_csv(req.file_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))

    summary = csv_service.data_summary(df, req.chart_type, req.x or csv_service.profile(df)["default_x"], req.series)
    cn_name = {"line": "折线图", "bar": "柱状图", "pie": "饼图",
               "scatter": "散点图", "radar": "雷达图", "heatmap": "相关性热力图",
               "table": "数据表格"}.get(req.chart_type, req.chart_type)

    prompt = f"""下面是真实实验数据的统计结果，请为这幅{cn_name}撰写学术论文 Figure Caption：

{summary}

要求：
1. 英文，80 词以内，单段
2. 以 "Fig. 1." 开头
3. 说明图展示的内容、坐标轴含义、以及数据体现的核心结论
4. 只依据上面给出的数据，不要编造数值"""
    caption = llm_chat(prompt, system="你是学术论文写作专家，擅长撰写规范的 Figure Caption。")
    return {"caption": caption.strip(), "summary": summary}


class ExportReq(ChartReq):
    target: str = "tikz"  # tikz | mermaid


@router.post("/export")
async def export_code(req: ExportReq):
    """把数据导出为 LaTeX TikZ 或 Mermaid 代码，便于直接嵌入论文"""
    try:
        df = csv_service.load_csv(req.file_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))

    small = df.head(20)
    table = small.to_csv(index=False, float_format="%.4f")
    if req.target == "tikz":
        prompt = f"""请把下面的数据转成 LaTeX TikZ 柱状图代码：

{table}

严格要求：
1. 使用 \\begin{{tikzpicture}} ... \\end{{tikzpicture}}
2. 只用基本的 \\draw / \\node / \\fill 和 axis-like 手动坐标
3. 必须包含坐标轴、刻度标签和数据柱
4. 只输出 LaTeX 代码，不要解释、不要 markdown 代码块"""
        system = "你是 LaTeX 专家，只输出可编译的 TikZ 代码。"
    else:
        prompt = f"""请把下面的数据转成 Mermaid 图表代码：

{table}

严格要求：
1. 使用 xychart-beta 语法，例如：
   xychart-beta
       title "示例"
       x-axis [a, b, c]
       y-axis "值" 0 --> 100
       bar [10, 20, 30]
2. 只输出 Mermaid 代码，不要解释、不要 markdown 代码块"""
        system = "你是 Mermaid 代码生成器，只输出有效代码。"

    code = llm_chat(prompt, system=system).strip()
    if "```" in code:
        parts = code.split("```")
        code = parts[1] if len(parts) > 1 else code
        if code.startswith(("latex", "tex", "mermaid", "tikz")):
            code = code.split("\n", 1)[1] if "\n" in code else code
    return {"target": req.target, "code": code.strip()}
