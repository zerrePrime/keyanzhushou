# 科研助手 Agent — 任务清单 & 项目交接

> 全国高校 AI 大模型挑战赛（赛题：多智能体科研助手 Agent）
> 省赛截止：2026-11-18

---

## 🗂 项目位置

```
D:\Program\chuanzhidemo
├── backend/          # FastAPI 后端（Python 3.13）
├── frontend/         # Vue 3 + Vite 前端
├── docker-compose.yml
├── nginx.conf
└── README.md
```

## ⚙️ 环境速查

| 项目 | 值 |
|---|---|
| Python | `D:\Program\python\python.exe`（只用 3.13，3.11 坏了放弃） |
| Node.js | 已装 |
| Ollama | 本地 `http://localhost:11434`，模型 `qwen2.5:7b` + `qwen2.5-coder:7b` |
| 显卡 | RTX 4060 8G |
| 网络 | **没有代理**，ollama.ai / hf-mirror.com 被墙 |
| 后端端口 | 8000 |
| 前端端口 | 5173 |

## 🚀 启动命令

```powershell
# 后端
cd D:\Program\chuanzhidemo\backend
D:\Program\python\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 前端
cd D:\Program\chuanzhidemo\frontend
npm.cmd run dev
```

---

## ✅ 已完成（截止 2026-10-26 晚）

### 后端 — 6 条路由全部注册 ✅

| 路由 | 文件 | 状态 |
|---|---|---|
| `/api/papers/*` | `api/routes/papers.py` | ✅ upload / list / delete / **新增 file 下载** |
| `/api/qa/ask` | `api/routes/qa.py` | ✅ 单文问答 / 多文对比 |
| `/api/arxiv/*` | `api/routes/arxiv.py` | ✅ search / daily |
| `/api/graph/*` | `api/routes/graph.py` | ✅ citation / survey |
| `/api/writing/*` | `api/routes/writing.py` | ✅ framework / diagram / caption |
| `/api/agent/*` | **新建** `api/routes/agent.py` | ✅ chat / tools / health |

**核心模块：**
- `rag/chroma_client.py` — Chroma + **ONNXMiniLM_L6_V2()**（无 providers 参数！首次下载 79MB 到 `~/.cache/chroma/`）
- `rag/pdf_parser.py` — PyMuPDF 切块（CHUNK=800, OVERLAP=100）
- `rag/qa_service.py` — RAG + ollama_chat + **中文→英文 fallback**（ZH_TO_EN 字典）
- `services/graph_service.py` — NetworkX PageRank + 引用图谱（目前是全连接 baseline）
- `agent/langgraph_agent.py` — LangGraph StateGraph（decide→execute→synthesize），**6 个 Tool**

### 前端 — 8 个页面全部升级 ✅

| 页面 | 核心能力 |
|---|---|
| App.vue | 侧边栏导航 + 后端在线状态 + 路由过渡动画 |
| PapersView.vue | 拖拽上传 + 进度条 + 卡片列表 |
| QAView.vue | 聊天气泡 + 单文/多文模式 + 溯源标签 |
| **AgentView.vue** 🆕 | LangGraph Agent 对话界面 + 工具面板 + 决策可视化 |
| ArxivView.vue | 卡片式论文列表 + PDF/Abstract 链接 |
| GraphView.vue | **ECharts 力导向图** + 基石论文高亮 + 节点交互 |
| WritingView.vue | **Mermaid 前端 SVG 渲染** + 框架生成 + Caption |
| ReaderView.vue | **PDF.js 完整集成** + 翻页缩放 + AI 摘要 |

**验证通过：** `npm run build` → ✓ built in 17.66s

### Docker — 已就绪 ✅
- `docker-compose.yml` / `Dockerfile` / `nginx.conf`

---

## 🔴 明天要做的（按优先级）

### P0 — 端到端联调（必须先做）

- [ ] **启动后端 + 前端，跑一遍完整流程**
  - 上传一篇 PDF → AgentView 问「文献库有什么论文」→ 看 Agent 回答对不对
  - QAView 问「这篇论文用了什么优化器」→ 看能否溯源到页码
  - GraphView 看图谱是否真的渲染出来（不是空白）
  - ReaderView 选一篇论文 → PDF.js 能否正常渲染
  - WritingView 生成 Mermaid → 是否真的渲染成 SVG
- [ ] **修所有跑不通的 bug**（这是最重要的！）

### P1 — LangGraph Agent 深度优化（比赛评分重点）

- [ ] Agent 多轮对话记忆（目前 `agent_chat(user_input)` 没有 history 参数生效）
- [ ] Agent 自动多工具串联（现在只调用一个工具就 synthesize，比赛要 Task Planning）
  - 例：用户问「RAG 最新进展并帮我写综述」→ 应该先 arxiv_search → 再 auto_survey
- [ ] Agent 工具调用参数提取（现在 `execute_tool` 把整个 user_input 当 query，粗糙）
- [ ] AgentView 界面加「思考链可视化」（比赛展示用，每一步 decision→tool→result 都要显示）

### P2 — RAG 质量提升

- [ ] **Rerank 重排**（bge-reranker-large 或用 CrossEncoder），chroma 检索后 rerank 前 10 条
- [ ] 真正的引用关系抽取（graph_service 目前是全连接 baseline，比赛需要真实引用边）
- [ ] PDF 切块改进：按段落切块而非固定 token size
- [ ] QA 中文问题不依赖 ZH_TO_EN 字典，尝试用英文 prompt 包装中文 query

### P3 — 前端补全

- [ ] **AgentView 多轮对话历史持久化**（刷新不丢）
- [ ] **GraphView 真实引用边可视化**（不是全连接图）
- [ ] **ReaderView 双栏对照翻译**（左原文右 AI 翻译）
- [ ] PapersView 加「预览」「删除确认」等小交互
- [ ] 移动端响应式优化

### P4 — 部署准备

- [ ] 租腾讯云轻量服务器（2核2G ~¥50/月）
- [ ] `docker-compose up -d` 一键部署
- [ ] 录 5-8 分钟演示视频
- [ ] 写技术文档 PDF（≤30 页）
- [ ] 提交 GitHub/Gitee 仓库 + 在线演示地址

---

## 🐛 已知坑 & 关键发现

| 坑 | 解法 |
|---|---|
| Python 3.11 的 pip/rich.pretty.py 有 null bytes | **只用 Python 3.13** |
| `ONNXMiniLM_L6_V2(providers=["CPUExecutionProvider"])` 报错 | 改成 `ONNXMiniLM_L6_V2()` — 这个类不接受 providers 参数 |
| Chroma 检索「找不到」 | 阈值从 0.7 放宽到 **0.9** + 加 `zh_to_en_query()` fallback |
| Swagger UI (swagger-ui.jsdelivr) 白屏 | 国内 CDN 被墙，不管它，前端 Vue 才是主 UI |
| Ollama / hf-mirror.com 被墙 | 放弃 Ollama Embedding，用 Chroma 内置 ONNX MiniLM（79MB 自动下载，慢但能下） |
| arxiv find(link, ns, {"title":"pdf"}) 报错 | find() 最多 2 参数，改成遍历 findall("atom:link") 后手动 get("title") |
| LangGraph `ToolNode` vs 手动调 Tool | 现在是手动调 tool.invoke()，没用 LangGraph 原生 ToolNode |

## 📂 可以清理的文件（临时测试脚本）

```
backend/check_adam.py
backend/check_chunks.py
backend/check_p7.py
backend/check_p7_chunks.py
backend/check_pages.py
backend/find_keywords.py
backend/test_rag.py
backend/test_rag2.py
```

## 📋 API 端点速查

```
GET  /health
GET  /api/papers/
POST /api/papers/upload     (multipart/form-data: file)
DELETE /api/papers/{paper_id}
GET  /api/papers/{paper_id}/file          ← PDF.js 下载

POST /api/qa/ask            {question, mode: single|compare, paper_ids?: []}

POST /api/arxiv/search      {query, max_results}
GET  /api/arxiv/daily

GET  /api/graph/citation
GET  /api/graph/survey

POST /api/writing/framework  {idea}
POST /api/writing/diagram   {description}
POST /api/writing/caption   {chart_type, data_summary}

POST /api/agent/chat        {message, history?}
GET  /api/agent/tools
GET  /api/agent/health
```

---

**祝顺利！比赛加油 💪**
