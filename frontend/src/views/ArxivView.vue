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
        <h3>
          📑 找到 {{ papers.length }} 篇论文
          <span v-if="!isSearch && skippedCount > 0" class="skipped-note">
            （本次已过滤 {{ skippedCount }} 篇已入库）
          </span>
        </h3>
        <button class="btn btn-ghost" @click="saveAll">💾 全部入库</button>
      </div>

      <div
        v-for="(p, i) in papers"
        :key="i"
        class="paper-card"
        :class="{ 'in-library': p.in_library }"
      >
        <div class="paper-header">
          <span class="arxiv-id">[{{ p.arxiv_id || `#${i + 1}` }}]</span>
          <span class="cats" v-if="p.categories">{{ p.categories.join(', ') }}</span>
          <span v-if="p.in_library" class="library-badge" :title="'库内: ' + (p.matched_title || p.title)">
            📚 已入库
          </span>
        </div>
        <h4 class="paper-title">{{ p.title }}</h4>
        <div class="paper-authors">{{ formatAuthors(p.authors) }}</div>
        <p class="paper-summary">{{ p.summary }}</p>
        <div class="paper-links">
          <a v-if="p.pdf_url" :href="p.pdf_url" target="_blank" class="link pdf">📄 PDF</a>
          <a v-if="p.abs_url" :href="p.abs_url" target="_blank" class="link abs">📎 Abstract</a>
          <button
            v-if="!p.in_library"
            class="link save"
            @click="saveOne(p, i)"
            :disabled="savingIdx === i"
          >
            {{ savingIdx === i ? '⏳ 下载解析中…' : '💾 入库' }}
          </button>
          <span v-else class="link saved">✅ 已在库中</span>
        </div>
      </div>
    </div>

    <div v-else-if="loading" class="card empty">
      <p>⏳ {{ isSearch ? '正在搜索论文，请稍候…' : '正在加载今日推送，请稍候…' }}</p>
    </div>

    <div v-else-if="searched && isSearch" class="card empty">
      <p>😕 没有找到相关论文，试试换个关键词</p>
    </div>

    <div v-else-if="searched" class="card empty">
      <p>😕 今天暂时没有推送内容，稍后再试试</p>
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
const savingIdx = ref(-1)
const skippedCount = ref(0)

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
  skippedCount.value = 0
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
    skippedCount.value = r.data.skipped_count || 0
  } catch (e) {
    alert('加载失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

const saveOne = async (p, idx) => {
  if (!p.pdf_url) return alert('这篇没有 PDF 链接')
  if (savingIdx.value !== -1) return
  savingIdx.value = idx
  try {
    const r = await axios.post('/api/arxiv/download', {
      url: p.pdf_url,
      filename: `${p.arxiv_id || 'paper'}.pdf`,
    })
    const d = r.data
    if (d.status === 'duplicate') {
      alert('⚠️ 已存在于库中，跳过重复入库：' + (d.title || p.title))
      markSaved(idx, d.title || p.title)
    } else if (d.detections && d.detections.length) {
      alert('✅ 已入库：' + (d.title || p.title) + '\n\n' + d.detections[0].suggestion)
      markSaved(idx, d.title || p.title)
    } else {
      alert('✅ 已入库：' + (d.title || p.title))
      markSaved(idx, d.title || p.title)
    }
  } catch (e) {
    alert('入库失败: ' + e.message)
  } finally {
    savingIdx.value = -1
  }
}

// 入库成功后即时把这张卡片标成已入库状态（不用重新搜）
const markSaved = (idx, matchedTitle) => {
  if (papers.value[idx]) {
    papers.value[idx].in_library = true
    papers.value[idx].matched_title = matchedTitle || papers.value[idx].title
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
.skipped-note { font-size: 12px; color: #888; font-weight: normal; margin-left: 6px; }

.paper-card {
  background: #fff; border-radius: 10px; padding: 18px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06); margin-bottom: 14px;
  border-left: 4px solid #4361ee; transition: all 0.2s;
}
.paper-card:hover { box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1); transform: translateY(-1px); }
.paper-card.in-library {
  background: #f7f8fa; border-left-color: #9ca3af; opacity: 0.78;
}
.paper-card.in-library:hover { opacity: 0.9; }

.library-badge {
  background: #e0f2fe; color: #0369a1; font-size: 11px;
  padding: 2px 8px; border-radius: 10px; font-weight: 600;
  margin-left: auto; cursor: help;
}

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
.link.save:disabled { opacity: 0.6; cursor: not-allowed; }
.link.saved {
  background: #f3f4f6; color: #6b7280; font-size: 12px;
  padding: 5px 12px; border-radius: 14px;
}
</style>
