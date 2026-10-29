<template>
  <div class="arxiv-page">
    <h1 class="page-title">🔎 arXiv 论文检索</h1>
    <p class="subtitle">搜索最新论文 / 每日推送，一键了解领域前沿</p>

    <div class="toolbar card">
      <input
        v-model="query"
        class="search-input"
        placeholder="输入关键词，如：transformer agent RAG fine-tuning"
        @keydown.enter.prevent="search"
      />
      <button class="btn btn-primary" @click="search" :disabled="!query.trim() || loading">
        {{ loading && isSearch ? '搜索中...' : '🔍 搜索' }}
      </button>
      <button class="btn btn-secondary" @click="daily" :disabled="loading">
        {{ loading && !isSearch ? '加载中...' : '📅 每日推送' }}
      </button>
    </div>

    <div v-if="papers.length" class="results">
      <div class="results-header">
        <h3>📑 找到 {{ papers.length }} 篇论文</h3>
        <button class="btn btn-ghost" @click="saveAll">💾 全部入库</button>
      </div>

      <div v-for="(p, i) in papers" :key="i" class="paper-card">
        <div class="paper-header">
          <span class="arxiv-id">[{{ p.arxiv_id || `#${i + 1}` }}]</span>
          <span class="cats" v-if="p.categories">{{ p.categories.join(', ') }}</span>
        </div>
        <h4 class="paper-title">{{ p.title }}</h4>
        <div class="paper-authors">{{ formatAuthors(p.authors) }}</div>
        <p class="paper-summary">{{ p.summary }}</p>
        <div class="paper-links">
          <a v-if="p.pdf_url" :href="p.pdf_url" target="_blank" class="link pdf">📄 PDF</a>
          <a v-if="p.abs_url" :href="p.abs_url" target="_blank" class="link abs">📎 Abstract</a>
          <button class="link save" @click="saveOne(p, i)">💾 入库</button>
        </div>
      </div>
    </div>

    <div v-else-if="searched" class="card empty">
      <p>😕 没有找到相关论文，试试换个关键词</p>
    </div>

    <div v-else class="card empty">
      <p>👈 输入关键词开始搜索，或点击「每日推送」看看今天有什么新鲜事</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import axios from 'axios'

const query = ref('')
const papers = ref([])
const loading = ref(false)
const isSearch = ref(true)
const searched = ref(false)

const formatAuthors = (authors) => {
  if (!authors || !authors.length) return ''
  if (authors.length <= 3) return authors.join(', ')
  return authors.slice(0, 3).join(', ') + ` 等 ${authors.length} 人`
}

const search = async () => {
  if (!query.value.trim() || loading.value) return
  loading.value = true
  isSearch.value = true
  papers.value = []
  searched.value = true
  try {
    const r = await axios.post('/api/arxiv/search', { query: query.value, max_results: 10 })
    papers.value = r.data.papers
  } catch (e) {
    alert('搜索失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

const daily = async () => {
  loading.value = true
  isSearch.value = false
  searched.value = true
  try {
    const r = await axios.get('/api/arxiv/daily')
    papers.value = r.data.papers
  } catch (e) {
    alert('加载失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

const saveOne = async (p, idx) => {
  // arXiv PDF 下载 → 临时文件 → upload
  if (!p.pdf_url) return alert('这篇没有 PDF 链接')
  try {
    const r = await axios.post('/api/arxiv/download', {
      url: p.pdf_url,
      filename: `${p.arxiv_id || 'paper'}.pdf`,
    })
    alert('✅ 已入库：' + (r.data.title || p.title))
  } catch (e) {
    alert('入库失败: ' + e.message)
  }
}

const saveAll = async () => {
  alert('批量入库功能开发中，可逐个点击「入库」')
}
</script>

<style scoped>
.arxiv-page { padding: 0; }
.page-title { font-size: 24px; margin-bottom: 4px; color: #1a1a2e; }
.subtitle { color: #888; margin-bottom: 20px; font-size: 13px; }

.toolbar {
  display: flex; gap: 10px; align-items: center; flex-wrap: wrap;
  margin-bottom: 20px;
}
.search-input {
  flex: 1; min-width: 280px; padding: 10px 16px; border-radius: 8px;
  border: 1px solid #ddd; font-size: 14px;
}
.search-input:focus { outline: none; border-color: #4361ee; }

.btn { padding: 10px 20px; border-radius: 8px; border: none; cursor: pointer; font-size: 14px; }
.btn-primary { background: #4361ee; color: #fff; }
.btn-primary:hover:not(:disabled) { background: #3a56d4; }
.btn-secondary { background: #6c757d; color: #fff; }
.btn-secondary:hover:not(:disabled) { background: #5a6268; }
.btn-ghost { background: transparent; color: #4361ee; border: 1px solid #4361ee; }
.btn-ghost:hover { background: #eef1ff; }
.btn:disabled { opacity: 0.6; cursor: not-allowed; }

.card {
  background: #fff; border-radius: 10px; padding: 22px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06);
}
.empty { text-align: center; color: #aaa; padding: 40px; }

.results-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 14px;
}
.results-header h3 { margin: 0; font-size: 16px; color: #1a1a2e; }

.paper-card {
  background: #fff; border-radius: 10px; padding: 18px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06); margin-bottom: 14px;
  border-left: 4px solid #4361ee; transition: all 0.2s;
}
.paper-card:hover { box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1); transform: translateY(-1px); }

.paper-header { display: flex; gap: 10px; align-items: center; margin-bottom: 8px; }
.arxiv-id {
  background: #f0f2ff; color: #4361ee; padding: 2px 8px;
  border-radius: 4px; font-family: monospace; font-size: 12px; font-weight: bold;
}
.cats { font-size: 11px; color: #7209b7; }

.paper-title { margin: 0 0 6px 0; font-size: 16px; color: #1a1a2e; line-height: 1.4; }
.paper-authors { font-size: 12px; color: #666; margin-bottom: 10px; }
.paper-summary {
  font-size: 13px; color: #444; line-height: 1.6;
  max-height: 100px; overflow: hidden; text-overflow: ellipsis;
  margin: 0 0 12px 0;
}

.paper-links { display: flex; gap: 10px; flex-wrap: wrap; }
.link {
  text-decoration: none; font-size: 12px; padding: 5px 12px;
  border-radius: 14px; transition: all 0.2s; cursor: pointer;
}
.link.pdf { background: #ffebee; color: #c62828; }
.link.pdf:hover { background: #c62828; color: #fff; }
.link.abs { background: #e3f2fd; color: #1565c0; }
.link.abs:hover { background: #1565c0; color: #fff; }
.link.save {
  background: #e8f5e9; color: #2e7d32; border: none;
}
.link.save:hover { background: #2e7d32; color: #fff; }
</style>
