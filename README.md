# Research Assistant Agent

> 全国高校 AI 大模型挑战赛作品 - 全流程科研助手 Agent

基于 **大语言模型 + LangGraph Agent 架构** 的全栈 Web 应用，覆盖科研工作者从文献管理、阅读问答、检索推荐到写作辅助的完整闭环。

---

## 核心特性（6 大模块）

| # | 模块 | 技术 |
|---|---|---|
| ① | PDF 管理与细粒度解析 | PyMuPDF + 语义去重 |
| ② | 抗幻觉 RAG 问答 | Chroma + ONNX MiniLM + 源头溯源 |
| ③ | 版式感知阅读 | PDF.js + 中英联动滚动 |
| ④ | arXiv 自动检索推荐 | arXiv API + 个性化相似度排序 |
| ⑤ | 引用图谱挖掘 | NetworkX + PageRank 基石论文 + 自动综述 |
| ⑥ | 学术写作 + 数据可视化 | Mermaid + ECharts + TikZ/Mermaid 导出 |

---

## Agent 工具链（7 个 Function Calling 工具）

LangGraph ReAct 循环，模型自主决定调用顺序，全程记录思考链（`thinking_trace`）：

| 工具 | 能力 |
|---|---|
| `rag_qa` | 文献库抗幻觉问答，答案带页码溯源 |
| `arxiv_search` | arXiv 实时检索最新论文 |
| `graph_analyze` | 引用图谱分析 + PageRank 基石论文 |
| `auto_survey` | 自动生成领域综述 |
| `write_framework` | 生成论文框架 |
| `list_papers` | 列出文献库所有论文 |
| `future_work` | 提取 Future Work，结合论文时间线**自动剔除已被后续工作解决的旧 idea** |

---

## 技术架构

整体分三层，数据单向流动：

- 前端层：Vue 3 + Vite + ECharts，负责页面展示与交互。
- 服务层：FastAPI 后端 + LangGraph Agent + Ollama LLM，负责业务编排、工具调用与模型推理。
- 数据层：Chroma 向量库 + ONNX Embedding + PyMuPDF，负责向量存储、语义检索与 PDF 解析。

请求链路：Vue 前端发起 HTTP 请求 → FastAPI 路由分发 → LangGraph Agent 按需调用工具或直接进入业务服务 → 读写 Chroma 向量库 / 解析 PDF → 结果逐层返回前端渲染。

### 模型栈（全本地化，零 API 费用）

| 类型 | 模型 | 用途 |
|---|---|---|
| LLM | **qwen2.5:7b** (Ollama) | RAG 问答 / 综述 / 框架生成 |
| Embedding | **ONNX MiniLM** (Chroma 内置) | 语义向量 / 相似度检索 |
| OCR | *（预留 PaddleOCR）* | 扫描件 PDF |

---

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- [Ollama](https://ollama.com/) + `qwen2.5:7b` 模型

### 1. 安装后端依赖

```powershell
cd backend
pip install -r requirements.txt
```

### 2. 启动后端

```powershell
# 双击 run_backend.bat 或
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API 文档：http://localhost:8000/docs

### 3. 安装前端依赖 & 启动

```powershell
cd frontend
npm install
npm run dev
```

访问：http://localhost:5173

---

## 环境变量配置

复制 `backend/.env.example` 为 `backend/.env` 后按需修改（**`.env` 不入库**）：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama` = 本地模型；`openai_compatible` = 云端 OpenAI 兼容 API |
| `OLLAMA_LLM_MODEL` | `qwen2.5:7b` | 本地 LLM 模型名 |
| `OPENAI_BASE_URL` | 阿里百炼兼容地址 | 云端 LLM 接入点 |
| `OPENAI_API_KEY` | 空 | 云端 API Key（**仅通过环境变量传入**） |
| `OPENAI_MODEL` | `qwen-plus` | 云端模型名 |
| `EMBEDDING_PROVIDER` | `onnx_mini_lm` | 固定为 Chroma 内置 ONNX MiniLM（384 维），**更换需重建向量库** |
| `CHROMA_PERSIST_DIR` | `d:\vue\chroma_db` | 向量库持久化目录 |
| `UPLOAD_DIR` | `d:\vue\uploads` | 上传文件目录 |

---

## Docker 一键部署

```bash
docker-compose up -d backend ollama
# 前端静态文件挂 nginx（可选）
docker-compose --profile serve-frontend up -d
```

---

## 项目结构

```
keyanzhushou/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── main.py            # 入口 + 路由挂载
│   │   ├── config.py          # 全局配置
│   │   ├── rag/               # RAG 管道 + PDF 解析
│   │   ├── services/          # 业务服务（论文 / 图谱 / CSV 可视化）
│   │   ├── api/routes/        # API 路由
│   │   └── agent/             # LangGraph Agent
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── .env.example
│   └── run_backend.bat
├── frontend/                   # Vue 3 前端
│   ├── src/views/             # 页面（文献 / Agent / 阅读 / 检索 / 图谱 / 写作）
│   └── package.json
├── docker-compose.yml
└── nginx.conf
```

---

## API 一览

| 方法 | 路径 | 功能 |
|---|---|---|
| POST | `/api/papers/upload` | 上传 PDF（含语义去重检测）|
| GET | `/api/papers/` | 文献列表 |
| GET | `/api/papers/{id}/outline` | PDF 标题树（H1/H2/H3）|
| GET | `/api/papers/{id}/text?page=n` | 单页文本（划词翻译用）|
| DELETE | `/api/papers/{id}` | 删除论文 |
| POST | `/api/qa/ask` | RAG 问答（带溯源）|
| POST | `/api/qa/translate` | 中英对照翻译（划词 / 整页）|
| POST | `/api/agent/chat` | Agent 多工具串联（返回思考链）|
| GET | `/api/agent/tools` | Agent 工具清单 |
| POST | `/api/arxiv/search` | arXiv 检索 |
| GET | `/api/arxiv/daily` | 每日最新论文 |
| GET | `/api/graph/citation` | 引用图谱数据 |
| GET | `/api/graph/survey` | 自动综述 |
| POST | `/api/writing/framework` | 论文框架生成 |
| POST | `/api/writing/diagram` | Mermaid 架构图 |
| POST | `/api/writing/caption` | 学术图表 Caption |
| POST | `/api/csv/upload` | CSV 解析 + 列画像 + 图表推荐 |
| POST | `/api/csv/chart` | 生成 ECharts 图表配置 |
| POST | `/api/csv/caption` | 基于真实数据生成 Figure Caption |
| POST | `/api/csv/export` | 导出 LaTeX TikZ / Mermaid 代码 |

---

## 测试用例

比赛官方提供的 PDF 测试集：

- `1706.03762v7.pdf` — Transformer v7（标准矢量 PDF）
- `1706.03762v1.pdf` — Transformer v1（版本去重检测）
- `1706.03762v1_img.pdf` — Transformer 扫描版（OCR）
- `UnderstandingDeepLearning_02_09_26_C.pdf` — 541 页长文档

---

## 团队信息

| 项 | 内容 |
|---|---|
| 参赛赛道 | 全国高校 AI 大模型挑战赛 · 智领科研 |
| 成员 | 徐梓轩 |
| 联系邮箱 | 925158470@qq.com |

---

## License

MIT
