<template>
  <div class="writing-page">
    <h1 class="page-title">✍️ 学术写作 Copilot</h1>
    <p class="subtitle">AI 辅助论文框架、架构图、图表标注生成</p>

    <!-- ① 论文框架生成 -->
    <div class="card">
      <h3>① 📑 论文框架生成</h3>
      <textarea
        v-model="idea"
        class="textarea"
        placeholder="输入你的研究 idea，如：我想用图神经网络改进推荐系统中的冷启动问题"
        rows="2"
      ></textarea>
      <div class="actions">
        <button class="btn btn-primary" @click="genFramework" :disabled="fwLoading">
          {{ fwLoading ? '生成中...' : '🚀 生成框架' }}
        </button>
        <button v-if="framework" class="btn btn-ghost" @click="copy(framework)">📋 复制</button>
      </div>
      <div v-if="framework" class="result-box">
        <pre>{{ framework }}</pre>
      </div>
    </div>

    <!-- ② 架构图生成 (Mermaid) -->
    <div class="card">
      <h3>② 🏗️ 架构图生成 (Mermaid)</h3>
      <textarea
        v-model="diagramDesc"
        class="textarea"
        placeholder="描述你的架构，如：Encoder-Decoder 结构，中间加 Cross-Attention，输入是用户历史序列"
        rows="2"
      ></textarea>
      <div class="actions">
        <button class="btn btn-primary" @click="genDiagram" :disabled="diagLoading">
          {{ diagLoading ? '生成中...' : '🎨 生成架构图' }}
        </button>
        <button v-if="mermaidCode" class="btn btn-ghost" @click="copy(mermaidCode)">📋 复制代码</button>
        <button v-if="mermaidCode" class="btn btn-ghost" @click="toggleCode">
          {{ showCode ? '隐藏代码' : '查看代码' }}
        </button>
      </div>

      <div v-if="mermaidCode" class="mermaid-wrap">
        <div class="mermaid-svg" v-html="mermaidSvg"></div>
        <pre v-if="showCode" class="mermaid-code">{{ mermaidCode }}</pre>
      </div>
    </div>

    <!-- ③ 图表 Caption -->
    <div class="card">
      <h3>③ 📊 图表 Caption 生成</h3>
      <div class="caption-form">
        <select v-model="chartType" class="select">
          <option>折线图</option><option>柱状图</option><option>雷达图</option>
          <option>散点图</option><option>热力图</option><option>饼图</option>
        </select>
        <input
          v-model="dataSummary"
          class="input"
          placeholder="数据概要，如：模型 A 在 CIFAR-10 上比 baseline 提升 5.2%"
        />
      </div>
      <div class="actions">
        <button class="btn btn-primary" @click="genCaption" :disabled="capLoading">
          {{ capLoading ? '生成中...' : '💬 生成 Caption' }}
        </button>
        <button v-if="caption" class="btn btn-ghost" @click="copy(caption)">📋 复制</button>
      </div>
      <div v-if="caption" class="caption-result">
        <em>"{{ caption }}"</em>
      </div>
    </div>

    <!-- ④ CSV 数据可视化 -->
    <div class="card">
      <h3>④ 📈 CSV 数据可视化</h3>
      <p class="hint">上传实验数据 CSV，自动识别列类型、生成规范图表与 Figure Caption，可导出 TikZ / Mermaid</p>

      <input ref="fileInput" type="file" accept=".csv,.tsv,.txt" class="hidden-input" @change="onFile" />
      <div class="actions">
        <button class="btn btn-primary" @click="pickFile" :disabled="csvLoading">
          {{ csvLoading ? '解析中...' : '📁 选择 CSV 文件' }}
        </button>
        <span v-if="csvMeta" class="file-meta">
          {{ csvMeta.filename }} · {{ csvMeta.rows }} 行 × {{ csvMeta.cols }} 列
        </span>
      </div>

      <div v-if="csvMeta" class="csv-body">
        <!-- 图表类型 -->
        <div class="chips">
          <button
            v-for="s in csvMeta.suggestions"
            :key="s.type"
            class="chip"
            :class="{ active: chartType2 === s.type }"
            @click="pickChartType(s.type)"
          >{{ s.label }}</button>
        </div>

        <!-- 列选择 -->
        <div class="col-pickers">
          <label class="picker">
            <span>横轴</span>
            <select v-model="xCol" class="select">
              <option v-for="c in csvMeta.columns" :key="c.name" :value="c.name">
                {{ c.name }}（{{ c.type }}）
              </option>
            </select>
          </label>
          <div class="picker series-picker" v-if="csvMeta.numeric_columns.length">
            <span>数值列</span>
            <span class="checks">
              <label v-for="c in csvMeta.numeric_columns" :key="c">
                <input type="checkbox" :value="c" v-model="seriesCols" /> {{ c }}
              </label>
            </span>
          </div>
        </div>

        <div class="actions">
          <button class="btn btn-primary" @click="renderChart" :disabled="chartLoading || chartType2 === 'table'">
            {{ chartLoading ? '绘图中...' : '📊 生成图表' }}
          </button>
          <button class="btn btn-ghost" @click="genCsvCaption" :disabled="capLoading2 || chartType2 === 'table'">
            {{ capLoading2 ? '生成中...' : '💬 生成图注' }}
          </button>
          <button class="btn btn-ghost" @click="exportCode('tikz')" :disabled="expLoading">📐 导出 TikZ</button>
          <button class="btn btn-ghost" @click="exportCode('mermaid')" :disabled="expLoading">🧭 导出 Mermaid</button>
        </div>

        <!-- 数据表格 -->
        <table v-if="chartType2 === 'table'" class="preview-table">
          <thead>
            <tr><th v-for="c in csvMeta.columns" :key="c.name">{{ c.name }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in csvMeta.preview" :key="i">
              <td v-for="c in csvMeta.columns" :key="c.name">{{ row[c.name] }}</td>
            </tr>
          </tbody>
        </table>

        <!-- 图表 -->
        <div v-show="chartType2 !== 'table'" ref="chartRef" class="chart-box"></div>

        <div v-if="csvCaption" class="caption-result">
          <em>"{{ csvCaption }}"</em>
          <button class="btn btn-ghost btn-sm" @click="copy(csvCaption)">📋 复制</button>
        </div>

        <template v-if="exportResult">
          <div class="export-head">
            <strong>{{ exportTarget === 'tikz' ? 'LaTeX TikZ' : 'Mermaid' }} 代码</strong>
            <button class="btn btn-ghost btn-sm" @click="copy(exportResult)">📋 复制</button>
          </div>
          <pre class="mermaid-code">{{ exportResult }}</pre>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import axios from 'axios'
import mermaidLib from 'mermaid'
import * as echarts from 'echarts'

// 初始化 Mermaid 库
mermaidLib.initialize({
  startOnLoad: false,
  theme: 'default',
  flowchart: { htmlLabels: true, curve: 'basis' },
  securityLevel: 'loose',
})

const idea = ref('')
const framework = ref('')
const fwLoading = ref(false)

const diagramDesc = ref('')
const mermaidCode = ref('')
const mermaidSvg = ref('')
const diagLoading = ref(false)
const showCode = ref(false)

const chartType = ref('折线图')
const dataSummary = ref('')
const caption = ref('')
const capLoading = ref(false)

// ===== CSV 数据可视化状态 =====
const fileInput = ref(null)
const csvMeta = ref(null)
const csvLoading = ref(false)
const chartType2 = ref('bar')
const xCol = ref('')
const seriesCols = ref([])
const chartRef = ref(null)
const chartLoading = ref(false)
const csvCaption = ref('')
const capLoading2 = ref(false)
const exportTarget = ref('')
const exportResult = ref('')
const expLoading = ref(false)
let chartInstance = null

const copy = async (text) => {
  try {
    await navigator.clipboard.writeText(text)
    alert('已复制到剪贴板 ✓')
  } catch {
    alert('复制失败，请手动选择')
  }
}

const genFramework = async () => {
  if (!idea.value.trim()) return alert('请先输入研究 idea')
  fwLoading.value = true
  try {
    const r = await axios.post('/api/writing/framework', { idea: idea.value })
    framework.value = r.data.framework
  } catch (e) {
    alert('生成失败: ' + e.message)
  } finally {
    fwLoading.value = false
  }
}

const genDiagram = async () => {
  if (!diagramDesc.value.trim()) return alert('请先描述架构')
  diagLoading.value = true
  try {
    const r = await axios.post('/api/writing/diagram', { description: diagramDesc.value })
    mermaidCode.value = r.data.mermaid
  } catch (e) {
    alert('生成失败: ' + e.message)
  } finally {
    diagLoading.value = false
  }
}

const genCaption = async () => {
  if (!dataSummary.value.trim()) return alert('请输入数据概要')
  capLoading.value = true
  try {
    const r = await axios.post('/api/writing/caption', {
      chart_type: chartType.value,
      data_summary: dataSummary.value,
    })
    caption.value = r.data.caption
  } catch (e) {
    alert('生成失败: ' + e.message)
  } finally {
    capLoading.value = false
  }
}

const toggleCode = () => { showCode.value = !showCode.value }

// ===== CSV 数据可视化 =====
const pickFile = () => fileInput.value?.click()

const errMsg = (e) => e.response?.data?.detail || e.message

const onFile = async (e) => {
  const f = e.target.files?.[0]
  if (!f) return
  csvLoading.value = true
  csvMeta.value = null
  csvCaption.value = ''
  exportResult.value = ''
  try {
    const fd = new FormData()
    fd.append('file', f)
    const r = await axios.post('/api/csv/upload', fd)
    const data = r.data
    csvMeta.value = data
    xCol.value = data.default_x
    seriesCols.value = (data.numeric_columns || []).slice(0, 3)
    const first = (data.suggestions || []).find((s) => s.type !== 'table')
    chartType2.value = first ? first.type : 'table'
    if (chartType2.value !== 'table') {
      await nextTick()
      await renderChart()
    }
  } catch (err) {
    alert('CSV 解析失败: ' + errMsg(err))
  } finally {
    csvLoading.value = false
    if (fileInput.value) fileInput.value.value = ''
  }
}

const pickChartType = async (t) => {
  chartType2.value = t
  if (t !== 'table') {
    await nextTick()
    await renderChart()
  }
}

const renderChart = async () => {
  if (!csvMeta.value || chartType2.value === 'table') return
  chartLoading.value = true
  try {
    const r = await axios.post('/api/csv/chart', {
      file_id: csvMeta.value.file_id,
      chart_type: chartType2.value,
      x: xCol.value,
      series: seriesCols.value,
    })
    await nextTick()
    if (!chartRef.value) return
    if (!chartInstance) chartInstance = echarts.init(chartRef.value)
    chartInstance.setOption(r.data.option, true)
    chartInstance.resize()
  } catch (err) {
    alert('绘图失败: ' + errMsg(err))
  } finally {
    chartLoading.value = false
  }
}

const genCsvCaption = async () => {
  if (!csvMeta.value) return
  capLoading2.value = true
  try {
    const r = await axios.post('/api/csv/caption', {
      file_id: csvMeta.value.file_id,
      chart_type: chartType2.value,
      x: xCol.value,
      series: seriesCols.value,
    })
    csvCaption.value = r.data.caption
  } catch (err) {
    alert('生成失败: ' + errMsg(err))
  } finally {
    capLoading2.value = false
  }
}

const exportCode = async (target) => {
  if (!csvMeta.value) return
  expLoading.value = true
  try {
    const r = await axios.post('/api/csv/export', {
      file_id: csvMeta.value.file_id,
      chart_type: chartType2.value,
      x: xCol.value,
      series: seriesCols.value,
      target,
    })
    exportTarget.value = r.data.target
    exportResult.value = r.data.code
  } catch (err) {
    alert('导出失败: ' + errMsg(err))
  } finally {
    expLoading.value = false
  }
}

const onResize = () => chartInstance?.resize()
onMounted(() => window.addEventListener('resize', onResize))
onBeforeUnmount(() => {
  window.removeEventListener('resize', onResize)
  chartInstance?.dispose()
  chartInstance = null
})

// Mermaid 代码变化时渲染 SVG
watch(mermaidCode, async (code) => {
  if (!code) { mermaidSvg.value = ''; return }
  await nextTick()
  try {
    const id = 'mmd-' + Date.now()
    const { svg } = await mermaidLib.render(id, code)
    mermaidSvg.value = svg
  } catch (e) {
    mermaidSvg.value = `<p style="color:red">Mermaid 渲染失败：${e.message}</p>`
  }
})
</script>

<style scoped>
.writing-page { padding: 0; }
.page-title { font-size: 24px; margin-bottom: 4px; color: #1a1a2e; }
.subtitle { color: #888; margin-bottom: 20px; font-size: 13px; }

.card {
  background: #fff; border-radius: 10px; padding: 22px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06); margin-bottom: 20px;
}
.card h3 { margin: 0 0 14px 0; font-size: 16px; color: #1a1a2e; }

.textarea {
  width: 100%; padding: 12px; border-radius: 8px; border: 1px solid #e0e0e0;
  font-size: 14px; resize: vertical; box-sizing: border-box;
  font-family: inherit; transition: border 0.2s;
}
.textarea:focus { outline: none; border-color: #4361ee; }

.actions { display: flex; gap: 10px; margin-top: 12px; flex-wrap: wrap; }

.btn {
  padding: 8px 18px; border-radius: 6px; border: none; cursor: pointer;
  font-size: 14px; transition: all 0.2s;
}
.btn-primary { background: #4361ee; color: #fff; }
.btn-primary:hover:not(:disabled) { background: #3a56d4; }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
.btn-ghost {
  background: transparent; color: #4361ee; border: 1px solid #4361ee;
}
.btn-ghost:hover { background: #eef1ff; }

.result-box {
  margin-top: 14px; background: #f8f9ff; border-radius: 8px;
  padding: 14px; max-height: 400px; overflow: auto;
}
.result-box pre { margin: 0; white-space: pre-wrap; line-height: 1.7; font-size: 13px; }

.mermaid-wrap { margin-top: 14px; }
.mermaid-svg {
  background: #fafafa; border: 1px solid #eee; border-radius: 8px;
  padding: 20px; overflow: auto; text-align: center;
}
.mermaid-svg :deep(svg) { max-width: 100%; height: auto; }
.mermaid-code {
  margin-top: 10px; background: #1a1a2e; color: #e0e0e0;
  padding: 14px; border-radius: 8px; max-height: 250px; overflow: auto;
  font-size: 12px; font-family: 'Consolas', monospace;
}

.caption-form { display: flex; gap: 10px; flex-wrap: wrap; }
.select {
  padding: 10px 12px; border-radius: 6px; border: 1px solid #ddd;
  font-size: 14px; min-width: 120px;
}
.input {
  flex: 1; min-width: 200px; padding: 10px 12px;
  border-radius: 6px; border: 1px solid #ddd; font-size: 14px;
}

.caption-result {
  margin-top: 14px; background: #fffbe6; border-left: 4px solid #ffd60a;
  padding: 14px; border-radius: 0 8px 8px 0; font-size: 15px;
  line-height: 1.6;
}
.caption-result em { color: #7209b7; font-style: italic; }

/* ===== CSV 数据可视化 ===== */
.hint { color: #888; font-size: 12.5px; margin: -6px 0 14px 0; }
.hidden-input { display: none; }
.file-meta { font-size: 13px; color: #555; align-self: center; }

.csv-body { margin-top: 16px; }

.chips { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; }
.chip {
  padding: 6px 14px; border-radius: 16px; border: 1px solid #dfe3f0;
  background: #fff; color: #555; font-size: 13px; cursor: pointer;
  transition: all 0.2s;
}
.chip:hover { border-color: #4361ee; color: #4361ee; }
.chip.active { background: #4361ee; border-color: #4361ee; color: #fff; }

.col-pickers { display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 4px; }
.picker { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #555; }
.picker .select { min-width: 150px; padding: 6px 10px; font-size: 13px; }
.series-picker { align-items: flex-start; }
.checks { display: flex; gap: 12px; flex-wrap: wrap; }
.checks label { display: flex; align-items: center; gap: 4px; font-size: 13px; cursor: pointer; }

.preview-table {
  width: 100%; border-collapse: collapse; margin-top: 14px; font-size: 12.5px;
}
.preview-table th, .preview-table td {
  border: 1px solid #eceff5; padding: 7px 10px; text-align: left;
  max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.preview-table th { background: #f6f7fb; color: #333; font-weight: 600; }
.preview-table tbody tr:hover { background: #fafbff; }

.chart-box {
  width: 100%; height: 400px; margin-top: 14px;
  border: 1px solid #eee; border-radius: 8px; background: #fff;
}

.btn-sm { padding: 4px 10px; font-size: 12px; margin-left: 10px; }
.export-head {
  display: flex; align-items: center; margin-top: 14px;
  font-size: 13px; color: #333;
}
</style>
