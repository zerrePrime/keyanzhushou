"""CSV 数据可视化服务 - 解析 / 结构画像 / 图表配置生成 / 图注与导出"""
import uuid
from pathlib import Path

import pandas as pd

from app.config import settings

CSV_DIR = Path(settings.UPLOAD_DIR) / "_csv"
CSV_DIR.mkdir(parents=True, exist_ok=True)

MAX_ROWS = 2000       # 前端渲染上限，超出部分截断
PREVIEW_ROWS = 8


def _col_type(s: pd.Series) -> str:
    """列类型推断：numeric / datetime / categorical / text"""
    if pd.api.types.is_numeric_dtype(s):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"
    sample = s.dropna().astype(str).head(20)
    if len(sample):
        parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
        if parsed.notna().mean() > 0.8:
            return "datetime"
    n_unique = s.nunique(dropna=True)
    if len(s) and n_unique <= max(20, int(len(s) * 0.05)):
        return "categorical"
    return "text"


def load_csv(file_id: str) -> pd.DataFrame:
    """按 file_id 读回上传的 CSV（仅允许已保存的 id，避免路径穿越）"""
    path = CSV_DIR / f"{file_id}.csv"
    if not path.exists():
        raise FileNotFoundError("CSV 文件不存在，请重新上传")
    return pd.read_csv(path)


def save_csv(content: bytes, filename: str) -> str:
    file_id = uuid.uuid4().hex[:12]
    (CSV_DIR / f"{file_id}.csv").write_bytes(content)
    (CSV_DIR / f"{file_id}.name").write_text(filename, encoding="utf-8")
    return file_id


def _default_x(df: pd.DataFrame, numeric: list[str]) -> str:
    """默认横轴：优先时间列，其次类别列，最后行号"""
    types = {c: _col_type(df[c]) for c in df.columns}
    for c in df.columns:
        if types[c] == "datetime":
            return c
    for c in df.columns:
        if types[c] == "categorical":
            return c
    return df.columns[0]


def profile(df: pd.DataFrame) -> dict:
    """生成列画像 + 预览 + 推荐图表"""
    columns = []
    for c in df.columns:
        s = df[c]
        t = _col_type(s)
        info = {
            "name": str(c),
            "type": t,
            "missing": int(s.isna().sum()),
            "unique": int(s.nunique(dropna=True)),
        }
        if t == "numeric":
            info["min"] = round(float(s.min()), 4) if s.notna().any() else None
            info["max"] = round(float(s.max()), 4) if s.notna().any() else None
            info["mean"] = round(float(s.mean()), 4) if s.notna().any() else None
        columns.append(info)

    preview = [
        {str(k): ("" if pd.isna(v) else str(v)) for k, v in row.items()}
        for row in df.head(PREVIEW_ROWS).to_dict(orient="records")
    ]

    numeric = [c["name"] for c in columns if c["type"] == "numeric"]
    categorical = [c["name"] for c in columns if c["type"] in ("categorical", "datetime")]

    suggestions = []
    if numeric:
        suggestions.append({"type": "table", "label": "数据表格"})
        suggestions.append({"type": "bar", "label": "柱状图"})
        suggestions.append({"type": "line", "label": "折线图"})
        if len(numeric) >= 2:
            suggestions.append({"type": "scatter", "label": "散点图"})
            suggestions.append({"type": "heatmap", "label": "相关性热力图"})
            suggestions.append({"type": "radar", "label": "雷达图"})
        if categorical:
            suggestions.append({"type": "pie", "label": "饼图"})

    return {
        "rows": int(len(df)),
        "cols": int(len(df.columns)),
        "columns": columns,
        "preview": preview,
        "numeric_columns": numeric,
        "category_columns": categorical,
        "default_x": _default_x(df, numeric),
        "suggestions": suggestions,
    }


def _clean(v):
    """NaN / numpy 标量 → JSON 安全值"""
    if pd.isna(v):
        return None
    if hasattr(v, "item"):
        return v.item()
    return v


def build_option(df: pd.DataFrame, chart_type: str, x: str = "", series: list[str] | None = None) -> dict:
    """把 DataFrame 转成 ECharts option（前端直接 setOption）"""
    df = df.head(MAX_ROWS)
    numeric = [str(c) for c in df.columns if _col_type(df[c]) == "numeric"]
    x = x if x in df.columns else _default_x(df, numeric)
    series = [c for c in (series or []) if c in numeric] or numeric[:3]

    if not numeric:
        raise ValueError("CSV 中没有数值列，无法绘制图表")

    x_data = [_clean(v) for v in df[x].tolist()]

    if chart_type in ("line", "bar"):
        return {
            "tooltip": {"trigger": "axis"},
            "legend": {"data": series, "top": 8},
            "grid": {"left": 60, "right": 30, "top": 48, "bottom": 70},
            "xAxis": {
                "type": "category",
                "data": [str(v) for v in x_data],
                "axisLabel": {"rotate": 30 if len(x_data) > 8 else 0},
            },
            "yAxis": {"type": "value"},
            "series": [
                {"name": c, "type": chart_type, "data": [_clean(v) for v in df[c].tolist()],
                 "smooth": chart_type == "line"}
                for c in series
            ],
        }

    if chart_type == "pie":
        val = series[0]
        return {
            "tooltip": {"trigger": "item", "formatter": "{b}: {c} ({d}%)"},
            "legend": {"type": "scroll", "bottom": 0},
            "series": [{
                "type": "pie",
                "radius": ["35%", "62%"],
                "data": [
                    {"name": str(n), "value": _clean(v)}
                    for n, v in zip(x_data, df[val].tolist())
                ],
            }],
        }

    if chart_type == "scatter":
        x_col, y_col = x, series[0]
        return {
            "tooltip": {"trigger": "item"},
            "grid": {"left": 60, "right": 30, "top": 40, "bottom": 60},
            "xAxis": {"type": "value", "name": x_col},
            "yAxis": {"type": "value", "name": y_col},
            "series": [{
                "type": "scatter",
                "symbolSize": 8,
                "data": [[_clean(a), _clean(b)] for a, b in zip(df[x_col].tolist(), df[y_col].tolist())],
            }],
        }

    if chart_type == "radar":
        cols = series
        indicators = []
        for c in cols:
            mx = df[c].max()
            indicators.append({"name": c, "max": round(float(mx) * 1.15, 4) if mx == mx else 1})
        rows = df.head(6)
        return {
            "tooltip": {},
            "legend": {"bottom": 0},
            "radar": {"indicator": indicators, "radius": "60%"},
            "series": [{
                "type": "radar",
                "data": [
                    {"name": str(_clean(r[x]))[:20], "value": [_clean(r[c]) for c in cols]}
                    for _, r in rows.iterrows()
                ],
            }],
        }

    if chart_type == "heatmap":
        corr = df[numeric].corr(numeric_only=True).round(3)
        data = []
        for i, ri in enumerate(corr.index):
            for j, cj in enumerate(corr.columns):
                data.append([j, i, _clean(corr.loc[ri, cj])])
        return {
            "tooltip": {"position": "top"},
            "grid": {"left": 90, "right": 40, "top": 40, "bottom": 80},
            "xAxis": {"type": "category", "data": numeric, "axisLabel": {"rotate": 30}},
            "yAxis": {"type": "category", "data": numeric},
            "visualMap": {"min": -1, "max": 1, "calculable": True, "orient": "vertical",
                          "right": 0, "top": "center",
                          "inRange": {"color": ["#4361ee", "#f5f7ff", "#e63946"]}},
            "series": [{"type": "heatmap", "data": data,
                        "label": {"show": True, "fontSize": 11}}],
        }

    raise ValueError(f"不支持的图表类型: {chart_type}")


def data_summary(df: pd.DataFrame, chart_type: str, x: str, series: list[str]) -> str:
    """把数据压缩成给 LLM 看的统计摘要，避免整表塞进 prompt"""
    numeric = [c for c in (series or []) if c in df.columns]
    lines = [f"数据规模：{len(df)} 行 × {len(df.columns)} 列", f"图表类型：{chart_type}", f"横轴：{x}"]
    for c in numeric[:6]:
        s = df[c].dropna()
        if not len(s):
            continue
        trend = ""
        if len(s) >= 2:
            delta = float(s.iloc[-1] - s.iloc[0])
            trend = f"，首尾变化 {delta:+.4f}"
        lines.append(
            f"列 {c}：均值 {float(s.mean()):.4f}，最大 {float(s.max()):.4f}，"
            f"最小 {float(s.min()):.4f}{trend}"
        )
    head = df.head(5).to_string(index=False, max_cols=8)
    lines.append("前 5 行样例：\n" + head)
    return "\n".join(lines)
