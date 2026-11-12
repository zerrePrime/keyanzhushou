<template>
  <div class="reader-page">
    <h1 class="page-title">📖 版式感知阅读器</h1>
    <p class="subtitle">标题树导航 · PDF 原文 · 中英对照翻译，三者联动</p>

    <!-- 顶部控制栏 -->
    <div class="card toolbar-card">
      <div class="toolbar">
        <select v-model="selectedId" class="select" @change="loadPaper">
          <option value="">-- 选择论文 --</option>
          <option v-for="p in papers" :key="p.paper_id" :value="p.paper_id">
            {{ p.title }}
          </option>
        </select>

        <div class="page-nav" v-if="hasDoc">
          <button class="btn" @click="prevPage" :disabled="currentPage <= 1">◀ 上一页</button>
          <span class="page-info">{{ currentPage }} / {{ totalPages }}</span>
          <button class="btn" @click="nextPage" :disabled="currentPage >= totalPages">下一页 ▶</button>
        </div>

        <div class="zoom" v-if="hasDoc">
          <button class="btn" @click="zoomOut">−</button>
          <span>{{ Math.round(scale * 100) }}%</span>
          <button class="btn" @click="zoomIn">+</button>
        </div>

        <span class="stat" v-if="hasDoc">共 {{ totalPages }} 页</span>
      </div>
    </div>

    <!-- 三栏主体 -->
    <div class="three-col" v-if="selectedId">
      <!-- 左：版式标题树 -->
      <aside class="card outline-card">
        <h3>📑 论文目录</h3>
        <div v-if="loadingOutline" class="loading small">解析版式中...</div>
        <div v-else-if="!outline.length" class="hint-text small">
          未识别到标题结构（可能是扫描版 PDF）
        </div>
        <ul v-else class="outline-list">
          <li
            v-for="(item, idx) in outline"
            :key="idx"
            :class="['outline-item', 'lv' + item.level, { active: activeIdx === idx }]"
            :title="item.title"
            @click="jumpTo(idx)"
          >
            <span class="dot"></span>
            <span class="title">{{ item.title }}</span>
            <span class="page">p{{ item.page }}</span>
          </li>
        </ul>
      </aside>

      <!-- 中：PDF 渲染（含可选中文本层） -->
      <div class="card pdf-card">
        <h3>📄 原文（第 {{ currentPage }} 页）</h3>
        <div v-if="loadingPdf" class="loading">
          ⏳ 加载 PDF 中...<span v-if="loadingProgress"> {{ loadingProgress }}%</span>
        </div>
        <div v-else-if="rendering" class="loading">🎨 渲染中...</div>
        <!-- v-show 而非 v-if：canvas 节点必须常驻，PDF.js 才能在加载完成后往这里绘制 -->
        <div class="pdf-scroll" v-show="hasDoc && !loadingPdf">
          <div class="pdf-stage">
            <canvas ref="canvasRef" class="pdf-canvas"></canvas>
          </div>
        </div>
        <div v-if="selectedText" class="selection-bar">
          <span class="sel-text">已选中 {{ selectedText.length }} 字符</span>
          <button class="btn btn-primary btn-sm" @click="translateSelection" :disabled="translatingSel">
            {{ translatingSel ? '翻译中...' : '🌐 翻译选中' }}
          </button>
          <button class="btn btn-sm" @click="clearSelection">清除</button>
        </div>
      </div>

      <!-- 右：翻译面板 + 摘要 -->
      <div class="right-col">
        <div class="card translate-card">
          <h3>🌐 中英对照翻译</h3>
          <div class="trans-tools">
            <button class="btn btn-primary btn-sm" @click="translatePage" :disabled="translatingPage || !pageText">
              {{ translatingPage ? '翻译中...' : '翻译当前页' }}
            </button>
            <button v-if="!translatingWhole" class="btn btn-sm" @click="translateWhole" :disabled="!totalPages">
              整篇翻译
            </button>
            <button v-else class="btn btn-sm" @click="cancelWhole">停止</button>
            <button class="lang-switch" @click="toggleLang" :disabled="translatingPage || translatingWhole">
              目标：{{ targetLang === 'zh' ? '中文' : '英文' }}
            </button>
          </div>

          <div v-if="translatingWhole" class="progress">
            <div class="bar" :style="{ width: wholeProgress + '%' }"></div>
            <span class="progress-text">{{ wholeDone }} / {{ totalPages }} 页</span>
          </div>

          <div class="trans-body">
            <template v-if="selectionTranslation">
              <div class="trans-block selection">
                <div class="label">选中片段</div>
                <div class="trans-text">{{ selectionTranslation }}</div>
              </div>
            </template>

            <div v-if="translatingPage" class="loading small">AI 翻译中...</div>
            <template v-else-if="pageTranslation">
              <div class="trans-block">
                <div class="label">第 {{ currentPage }} 页译文</div>
                <div class="trans-text">{{ pageTranslation }}</div>
              </div>
            </template>
            <div v-else-if="!selectionTranslation" class="hint-text small">
              点击「翻译当前页」，或在 PDF 上划词后点「翻译选中」
            </div>
          </div>
        </div>

        <div class="card">
          <h3>🤖 当前页 AI 摘要</h3>
          <div v-if="summarizing" class="loading small">AI 思考中...</div>
          <div v-else-if="pageSummary" class="summary-text">{{ pageSummary }}</div>
          <div v-else class="hint-text small">渲染完成后点击「生成摘要」</div>
          <button
            class="btn btn-primary btn-sm"
            style="margin-top:12px"
            @click="summarizePage"
            :disabled="summarizing || !currentPage"
          >
            ✨ 生成当前页摘要
          </button>
        </div>
      </div>
    </div>

    <div v-if="!selectedId" class="card empty-hint">
      <p>👈 请先在「论文管理」上传 PDF，或从上方选择一篇论文开始阅读。</p>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import axios from 'axios'

// pdf.js / pdf-viewer.js 从 index.html 移除，改为首次进入阅读器时按需加载
// 避免其他页面（登录页、RAG 问答等）被迫下载 503KB 的 pdf.js
let viewer = null                  // ← 模块顶层变量，prevPage/jumpTo/zoom 等闭包都引用它
let _viewerPromise = null
function ensurePdfViewer() {
  if (viewer) return viewer        // 已加载过直接返回
  if (_viewerPromise) return _viewerPromise  // 首次加载中，共享 Promise

  _viewerPromise = new Promise((resolve, reject) => {
    const load = (src) => new Promise((res, rej) => {
      const s = document.createElement('script')
      s.src = src
      s.onload = res
      s.onerror = () => rej(new Error('加载失败: ' + src))
      document.head.appendChild(s)
    })

    // 顺序：先 pdf.js（暴露 window.pdfjsLib），再 pdf-viewer.js（暴露 window.PDFViewer）
    load('/pdf.js')
      .then(() => load('/pdf-viewer.js'))
      .then(() => {
        if (!window.PDFViewer) reject(new Error('PDFViewer 初始化失败'))
        else {
          viewer = window.PDFViewer   // 赋值模块顶层
          resolve(viewer)
        }
      })
      .catch(reject)
  })
  return _viewerPromise
}

const papers = ref([])
const selectedId = ref('')
const totalPages = ref(0)
const currentPage = ref(1)
const scale = ref(1.2)

const canvasRef = ref(null)
const loadingPdf = ref(false)
const loadingProgress = ref(0)
const rendering = ref(false)
const pageText = ref('')
const pageSummary = ref('')
const summarizing = ref(false)
const hasDoc = ref(false)

// 目录树
const outline = ref([])
const loadingOutline = ref(false)
const activeIdx = ref(-1)

// 翻译
const targetLang = ref('zh')
const selectedText = ref('')
const selectionTranslation = ref('')
const translatingSel = ref(false)
const translatingPage = ref(false)
const translationCache = ref({})   // { 页码: 译文 }
const translatingWhole = ref(false)
const wholeDone = ref(0)
let wholeCancelled = false

const pageTranslation = computed(() => translationCache.value[currentPage.value] || '')
const wholeProgress = computed(() =>
  totalPages.value ? Math.round((wholeDone.value / totalPages.value) * 100) : 0
)

// 加载论文列表
onMounted(async () => {
  document.addEventListener('mouseup', onMouseUp)
  try {
    const r = await axios.get('/api/papers/')
    papers.value = r.data.papers
  } catch (e) {
    console.error('加载论文列表失败:', e)
  }
})

onUnmounted(() => {
  document.removeEventListener('mouseup', onMouseUp)
})

// 选择论文 → 加载 PDF + 目录
const loadPaper = async () => {
  if (!selectedId.value) return
  try {
    await ensurePdfViewer()  // 赋值模块顶层 viewer
  } catch (e) {
    alert('PDF 阅读器加载失败: ' + e.message)
    return
  }
  // 先把上一份 PDF 的画面擦掉，否则新文件加载期间页面里仍是旧论文
  viewer.clear()
  totalPages.value = 0
  loadingPdf.value = true
  loadingProgress.value = 0
  pageSummary.value = ''
  pageText.value = ''
  selectionTranslation.value = ''
  selectedText.value = ''
  translationCache.value = {}
  currentPage.value = 1
  hasDoc.value = false
  outline.value = []
  activeIdx.value = -1
  loadOutline()

  try {
    await nextTick()  // 确保 canvas 已挂载
    const url = `/api/papers/${selectedId.value}/file`
    const pages = await viewer.open(url, canvasRef.value, (p) => {
      loadingProgress.value = p
    })
    totalPages.value = pages
    hasDoc.value = true
    const result = await viewer.render(1)
    currentPage.value = result.pageNum
    scale.value = result.scale
    pageText.value = result.text
    syncOutline(result.pageNum)
  } catch (e) {
    console.error('PDF 加载失败:', e)
    alert('PDF 加载失败: ' + e.message)
    hasDoc.value = false
  } finally {
    loadingPdf.value = false
    loadingProgress.value = 0
  }
}

// 版式标题树
const loadOutline = async () => {
  loadingOutline.value = true
  try {
    const r = await axios.get(`/api/papers/${selectedId.value}/outline`)
    outline.value = r.data.outline || []
    if (outline.value.length) activeIdx.value = 0
  } catch (e) {
    console.error('目录解析失败:', e)
  } finally {
    loadingOutline.value = false
  }
}

// 目录 ↔ PDF 联动：点击标题跳页
const jumpTo = async (idx) => {
  const item = outline.value[idx]
  if (!item || !hasDoc.value) return
  activeIdx.value = idx
  await doRender(viewer.render(item.page))
}

// PDF 翻页 → 反查当前所在标题并高亮
const syncOutline = (page) => {
  if (!outline.value.length) return
  let idx = 0
  for (let i = 0; i < outline.value.length; i++) {
    if (outline.value[i].page <= page) idx = i
    else break
  }
  activeIdx.value = idx
}

const doRender = async (promise) => {
  if (!viewer) return
  rendering.value = true
  try {
    const result = await promise
    currentPage.value = result.pageNum
    scale.value = result.scale
    pageText.value = result.text
    pageSummary.value = ''
    syncOutline(result.pageNum)
  } catch (e) {
    console.error('渲染失败:', e)
  } finally {
    rendering.value = false
  }
}

const prevPage = () => doRender(viewer.prevPage())
const nextPage = () => doRender(viewer.nextPage())
const zoomIn = () => doRender(viewer.zoomIn())
const zoomOut = () => doRender(viewer.zoomOut())

// 划词：只在 PDF 文本层内的选区生效
const onMouseUp = () => {
  const sel = window.getSelection()
  if (!sel || sel.isCollapsed) return
  const text = sel.toString().trim()
  if (text.length < 2) return
  const layer = document.querySelector('.pdf-text-layer')
  const anchor = sel.anchorNode
  if (!layer || !anchor) return
  const node = anchor.nodeType === 3 ? anchor.parentNode : anchor
  if (!layer.contains(node)) return
  selectedText.value = text.slice(0, 3000)
}

const clearSelection = () => {
  selectedText.value = ''
  selectionTranslation.value = ''
  const sel = window.getSelection()
  if (sel) sel.removeAllRanges()
}

const toggleLang = () => {
  targetLang.value = targetLang.value === 'zh' ? 'en' : 'zh'
}

const translateSelection = async () => {
  if (!selectedText.value) return
  translatingSel.value = true
  try {
    const r = await axios.post('/api/qa/translate', {
      text: selectedText.value,
      target: targetLang.value,
    })
    selectionTranslation.value = r.data.text
  } catch (e) {
    alert('翻译失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    translatingSel.value = false
  }
}

const translatePage = async () => {
  if (!pageText.value) return
  translatingPage.value = true
  try {
    const r = await axios.post('/api/qa/translate', {
      text: pageText.value,
      target: targetLang.value,
    })
    translationCache.value[currentPage.value] = r.data.text
  } catch (e) {
    alert('翻译失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    translatingPage.value = false
  }
}

// 整篇翻译：按页串行请求，逐页写入缓存，切页即可看到译文
const translateWhole = async () => {
  if (!selectedId.value || !totalPages.value) return
  translatingWhole.value = true
  wholeCancelled = false
  wholeDone.value = 0
  try {
    for (let p = 1; p <= totalPages.value; p++) {
      if (wholeCancelled) break
      if (translationCache.value[p]) {
        wholeDone.value = p
        continue
      }
      const tr = await axios.get(`/api/papers/${selectedId.value}/text`, { params: { page: p } })
      const text = (tr.data.text || '').trim()
      if (text) {
        const r = await axios.post('/api/qa/translate', { text, target: targetLang.value })
        translationCache.value[p] = r.data.text
      } else {
        translationCache.value[p] = '(本页无可提取文字)'
      }
      wholeDone.value = p
    }
  } catch (e) {
    alert('整篇翻译中断: ' + (e.response?.data?.detail || e.message))
  } finally {
    translatingWhole.value = false
  }
}

const cancelWhole = () => {
  wholeCancelled = true
}

// AI 生成当前页摘要
const summarizePage = async () => {
  if (!pageText.value || !selectedId.value) return
  summarizing.value = true
  try {
    const r = await axios.post('/api/qa/ask', {
      question: `请用中文总结以下内容的核心要点（3-5 句话）：\n${pageText.value.slice(0, 1500)}`,
    })
    pageSummary.value = r.data.answer
  } catch (e) {
    alert('摘要生成失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    summarizing.value = false
  }
}
</script>

<style scoped>
.reader-page { padding: 0; }
.page-title { font-size: 24px; margin-bottom: 4px; color: #1a1a2e; }
.subtitle { color: #888; margin-bottom: 16px; font-size: 13px; }

.toolbar-card { padding: 14px 20px; margin-bottom: 16px; }
.toolbar {
  display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
}
.select {
  padding: 8px 14px; border-radius: 6px; border: 1px solid #ddd;
  font-size: 14px; min-width: 280px;
}
.page-nav { display: flex; gap: 8px; align-items: center; }
.page-info { font-size: 13px; color: #666; font-family: monospace; min-width: 70px; text-align: center; }
.zoom { display: flex; gap: 8px; align-items: center; font-size: 13px; font-family: monospace; }
.stat { margin-left: auto; font-size: 13px; color: #888; }

.btn {
  padding: 7px 14px; border-radius: 6px; border: 1px solid #ddd; background: #fff;
  color: #333; cursor: pointer; font-size: 13px; transition: all 0.2s;
}
.btn span, .zoom span { color: #333; }
.btn:hover:not(:disabled) { background: #f0f2ff; border-color: #4361ee; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-primary { background: #4361ee; color: #fff; border-color: #4361ee; }
.btn-primary:hover:not(:disabled) { background: #3a56d4; }
.btn-sm { padding: 5px 10px; font-size: 12px; }

.three-col {
  display: grid;
  grid-template-columns: 230px minmax(0, 2fr) minmax(0, 1.15fr);
  gap: 16px;
  align-items: start;
}
@media (max-width: 1200px) {
  .three-col { grid-template-columns: 200px minmax(0, 1fr); }
  .right-col { grid-column: 1 / -1; }
}
@media (max-width: 800px) {
  .three-col { grid-template-columns: 1fr; }
}

.card {
  background: #fff; border-radius: 10px; padding: 18px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06); margin-bottom: 16px;
}
.card h3 { margin: 0 0 14px 0; font-size: 15px; color: #1a1a2e; }

/* 目录树 */
.outline-card { position: sticky; top: 16px; max-height: calc(100vh - 120px); overflow-y: auto; }
.outline-list { list-style: none; margin: 0; padding: 0; }
.outline-item {
  display: flex; align-items: baseline; gap: 6px;
  padding: 6px 8px; border-radius: 6px; cursor: pointer;
  font-size: 13px; color: #444; line-height: 1.45;
  border-left: 2px solid transparent;
}
.outline-item:hover { background: #f5f7ff; }
.outline-item.active { background: #eef1ff; color: #4361ee; border-left-color: #4361ee; }
.outline-item .title {
  flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.outline-item .dot {
  width: 4px; height: 4px; border-radius: 50%; background: #c9cfe4; flex: none;
}
.outline-item .page { font-size: 11px; color: #aaa; font-family: monospace; flex: none; }
.outline-item.lv1 { font-weight: 600; font-size: 13.5px; }
.outline-item.lv1 .dot { background: #4361ee; width: 6px; height: 6px; }
.outline-item.lv2 { padding-left: 18px; }
.outline-item.lv3 { padding-left: 32px; font-size: 12.5px; color: #666; }

/* PDF */
.pdf-card { overflow: hidden; }
.pdf-scroll { overflow: auto; max-height: calc(100vh - 220px); text-align: center; }
.pdf-stage { position: relative; display: inline-block; line-height: 0; }
.pdf-canvas {
  display: block; border: 1px solid #eee; border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}
:deep(.pdf-text-layer) {
  position: absolute; top: 0; left: 0; overflow: hidden; line-height: 1;
}
:deep(.pdf-text-layer span) {
  color: transparent; position: absolute; white-space: pre;
  transform-origin: 0 0; cursor: text;
}
:deep(.pdf-text-layer span::selection) { background: rgba(67, 97, 238, 0.35); }

.selection-bar {
  margin-top: 10px; display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; background: #f5f7ff; border-radius: 8px;
}
.sel-text { font-size: 12px; color: #4361ee; margin-right: auto; }

.loading { text-align: center; color: #888; padding: 30px; font-size: 13px; }
.loading.small { padding: 12px 0; }

/* 翻译面板 */
.trans-tools { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }
.lang-switch {
  margin-left: auto; border: 1px solid #d9defc; background: #eef1ff; color: #4361ee;
  padding: 5px 10px; border-radius: 999px; font-size: 12px; cursor: pointer;
}
.lang-switch:disabled { opacity: 0.55; cursor: not-allowed; }

.progress {
  position: relative; height: 8px; background: #eef0f6; border-radius: 999px;
  margin-bottom: 12px; overflow: visible;
}
.progress .bar {
  height: 100%; background: linear-gradient(90deg, #4361ee, #7c8ff5);
  border-radius: 999px; transition: width 0.3s;
}
.progress-text {
  position: absolute; right: 0; top: 12px; font-size: 11px; color: #888;
  font-family: monospace;
}

.trans-body { max-height: 420px; overflow-y: auto; margin-top: 8px; }
.trans-block { margin-bottom: 14px; }
.trans-block .label {
  font-size: 11px; color: #888; margin-bottom: 6px; letter-spacing: 0.5px;
}
.trans-block.selection .label { color: #4361ee; }
.trans-text {
  font-size: 13.5px; line-height: 1.85; color: #333;
  white-space: pre-wrap; background: #f8f9ff; padding: 12px; border-radius: 8px;
}
.trans-block.selection .trans-text { background: #eef2ff; }

.summary-text {
  line-height: 1.8; font-size: 13.5px; background: #f8f9ff;
  padding: 14px; border-radius: 8px;
}
.hint-text { color: #aaa; font-size: 12.5px; line-height: 1.7; }

.empty-hint { text-align: center; color: #aaa; padding: 40px; }
</style>
