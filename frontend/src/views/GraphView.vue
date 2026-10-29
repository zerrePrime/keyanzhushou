<template>
  <div class="graph-page">
    <h1 class="page-title">🕸️ 引用图谱分析</h1>

    <!-- 操作栏 -->
    <div class="toolbar">
      <button class="btn btn-primary" @click="load" :disabled="loading">
        {{ loading ? '加载中...' : '🔄 刷新图谱' }}
      </button>
      <button class="btn btn-secondary" @click="survey" :disabled="surveying">
        {{ surveying ? '生成中...' : '📝 生成综述' }}
      </button>
      <span class="stat" v-if="graph.nodes.length">
        节点: {{ graph.nodes.length }} | 边: {{ graph.edges.length }}
      </span>
    </div>

    <div class="two-col">
      <!-- 左：ECharts 图谱 -->
      <div class="card graph-card">
        <h3>🔗 引用关系拓扑</h3>
        <div ref="chartRef" class="chart-box"></div>
        <p class="hint">💡 拖拽节点可移动，滚轮缩放，悬停查看论文标题</p>
      </div>

      <!-- 右：基石论文 + 节点详情 -->
      <div class="right-col">
        <div class="card">
          <h3>🏆 基石论文 Top 5</h3>
          <div v-if="topCited.length === 0" class="empty">
            先上传一些论文再看图谱吧
          </div>
          <div
            v-for="(t, i) in topCited"
            :key="i"
            class="foundation-item"
            :class="{ active: selectedNode === t.paper_id }"
            @click="focusNode(t.paper_id)"
          >
            <span class="rank">#{{ i + 1 }}</span>
            <span class="ftitle">{{ shorten(t.title, 40) }}</span>
            <span class="pr">{{ t.pagerank }}</span>
          </div>
        </div>

        <div class="card" v-if="nodeInfo">
          <h3>📄 节点详情</h3>
          <p><strong>标题：</strong>{{ nodeInfo.title }}</p>
          <p><strong>Paper ID：</strong><code>{{ nodeInfo.id }}</code></p>
        </div>

        <div class="card" v-if="surveyText">
          <h3>📝 自动综述</h3>
          <p class="survey-text">{{ surveyText }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import axios from 'axios'
import * as echarts from 'echarts'

const loading = ref(false)
const surveying = ref(false)
const topCited = ref([])
const graph = ref({ nodes: [], edges: [] })
const surveyText = ref('')
const selectedNode = ref('')
const nodeInfo = ref(null)

const chartRef = ref(null)
let chartInstance = null

const shorten = (s, n) => (s && s.length > n ? s.slice(0, n) + '...' : s)

const load = async () => {
  loading.value = true
  try {
    const r = await axios.get('/api/graph/citation')
    topCited.value = r.data.top_cited
    graph.value = r.data
    await nextTick()
    renderChart()
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

const survey = async () => {
  surveying.value = true
  try {
    const r = await axios.get('/api/graph/survey')
    surveyText.value = r.data.survey
  } catch (e) {
    console.error(e)
  } finally {
    surveying.value = false
  }
}

const renderChart = () => {
  if (!chartRef.value) return

  if (chartInstance) chartInstance.dispose()
  chartInstance = echarts.init(chartRef.value)

  const nodes = graph.value.nodes.map((n) => {
    const isFoundation = topCited.value.some((t) => t.paper_id === n.id)
    return {
      id: n.id,
      name: shorten(n.title || n.id, 25),
      symbolSize: isFoundation ? 55 : 35,
      category: isFoundation ? 0 : 1,
      itemStyle: {
        color: isFoundation ? '#4361ee' : '#7209b7',
        borderColor: isFoundation ? '#ffd60a' : 'transparent',
        borderWidth: isFoundation ? 3 : 0,
      },
      label: { show: true, fontSize: 11, color: '#333' },
    }
  })

  const edges = graph.value.edges.map((e) => ({
    source: e.source,
    target: e.target,
    lineStyle: { color: '#aaa', width: 1.2, curveness: 0.1 },
  }))

  const option = {
    tooltip: {
      formatter: (p) => {
        if (p.dataType === 'edge') return `${p.data.source} → ${p.data.target}`
        return `<b>${p.data.name}</b><br/>ID: ${p.data.id}`
      },
    },
    legend: [{ data: ['基石论文', '普通论文'] }],
    series: [
      {
        type: 'graph',
        layout: 'force',
        roam: true,
        draggable: true,
        data: nodes,
        links: edges,
        categories: [{ name: '基石论文' }, { name: '普通论文' }],
        force: {
          repulsion: 400,
          gravity: 0.15,
          edgeLength: [80, 200],
          layoutAnimation: true,
        },
        emphasis: {
          focus: 'adjacency',
          lineStyle: { width: 3 },
        },
      },
    ],
  }

  chartInstance.setOption(option)
  chartInstance.on('click', (p) => {
    if (p.dataType === 'node') {
      selectedNode.value = p.data.id
      nodeInfo.value = { id: p.data.id, title: p.data.name }
    }
  })
}

const focusNode = (id) => {
  selectedNode.value = id
  const n = graph.value.nodes.find((x) => x.id === id)
  if (n) nodeInfo.value = n
  if (chartInstance) {
    chartInstance.dispatchAction({ type: 'focusNodeAdjacency', id })
  }
}

const handleResize = () => chartInstance && chartInstance.resize()

onMounted(() => {
  load()
  window.addEventListener('resize', handleResize)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (chartInstance) chartInstance.dispose()
})

watch(graph, () => {
  if (graph.value.nodes.length > 0) renderChart()
}, { deep: true })
</script>

<style scoped>
.graph-page { padding: 0; }
.page-title { font-size: 24px; margin-bottom: 20px; color: #1a1a2e; }

.toolbar {
  display: flex; gap: 12px; align-items: center; margin-bottom: 20px; flex-wrap: wrap;
}
.stat { margin-left: auto; font-size: 13px; color: #888; }

.btn {
  padding: 8px 18px; border-radius: 6px; border: none; cursor: pointer;
  font-size: 14px; transition: all 0.2s;
}
.btn-primary { background: #4361ee; color: #fff; }
.btn-primary:hover:not(:disabled) { background: #3a56d4; }
.btn-secondary { background: #6c757d; color: #fff; }
.btn-secondary:hover:not(:disabled) { background: #5a6268; }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }

.two-col { display: grid; grid-template-columns: 2fr 1fr; gap: 20px; }
@media (max-width: 900px) { .two-col { grid-template-columns: 1fr; } }

.card {
  background: #fff; border-radius: 10px; padding: 20px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06); margin-bottom: 16px;
}
.card h3 { margin: 0 0 14px 0; font-size: 16px; color: #1a1a2e; }

.graph-card { height: 520px; display: flex; flex-direction: column; }
.chart-box { flex: 1; min-height: 400px; }
.hint { margin-top: 8px; font-size: 12px; color: #999; }

.foundation-item {
  display: flex; gap: 10px; align-items: center; padding: 10px 12px;
  background: #f8f9ff; border-radius: 8px; margin-bottom: 8px; cursor: pointer;
  transition: all 0.2s;
}
.foundation-item:hover { background: #e8eaff; transform: translateX(3px); }
.foundation-item.active { background: #4361ee; color: #fff; }
.rank { font-weight: bold; color: '#4361ee'; min-width: 30px; }
.foundation-item.active .rank { color: '#ffd60a'; }
.ftitle { flex: 1; font-size: 13px; }
.pr { font-family: monospace; font-size: 12px; color: #7209b7; }
.foundation-item.active .pr { color: #ffd60a; }

.survey-text { line-height: 1.8; font-size: 14px; color: #333; white-space: pre-wrap; }
.empty { color: #aaa; font-size: 13px; padding: 10px; }

code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; font-size: 12px; }
</style>
