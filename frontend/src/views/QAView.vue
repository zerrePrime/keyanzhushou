<template>
  <div class="qa-page">
    <h1 class="page-title">💬 RAG 智能问答</h1>
    <p class="subtitle">在已上传文献库中提问，答案带原文溯源（支持多文对比）</p>

    <div class="qa-layout">
      <!-- 左：输入 -->
      <div class="card input-card">
        <h3>❓ 提问</h3>
        <textarea
          v-model="question"
          class="textarea"
          placeholder="例如：这篇论文用了什么优化器？Adam 和 SGD 有什么区别？"
          rows="3"
          @keydown.enter.exact.prevent="ask"
        ></textarea>
        <div class="controls">
          <div class="mode-switch">
            <button
              class="mode-btn"
              :class="{ active: mode === 'single' }"
              @click="mode = 'single'"
            >📚 文献库问答</button>
            <button
              class="mode-btn"
              :class="{ active: mode === 'compare' }"
              @click="mode = 'compare'"
            >⚖️ 多文对比</button>
          </div>
          <select v-if="mode === 'single'" v-model="paperId" class="paper-select">
            <option value="">🌐 全库检索（所有论文）</option>
            <option v-for="p in papers" :key="p.paper_id" :value="p.paper_id">
              📄 {{ p.title || p.paper_id }}
            </option>
          </select>
          <button class="btn btn-primary" @click="ask" :disabled="!question.trim() || loading">
            {{ loading ? '思考中...' : '🚀 发送' }}
          </button>
        </div>
        <p v-if="paperId" class="scope-tip">
          🔒 当前仅在《{{ currentPaperTitle }}》内检索，库内其他论文不参与
        </p>
      </div>

      <!-- 右：结果 -->
      <div class="results-area">
        <div v-if="!answer && !loading" class="card empty-card">
          <p>👆 在上方输入问题，答案将显示在这里</p>
          <div class="quick">
            <button class="chip" @click="question = '这篇论文的主要贡献是什么？'; ask()">主要贡献</button>
            <button class="chip" @click="question = '实验用了什么数据集和模型？'; ask()">实验设置</button>
            <button class="chip" @click="question = 'Adam 优化器的收敛速度比 SGD 快吗？'; ask()">优化器对比</button>
          </div>
        </div>

        <div v-if="loading" class="card loading-card">
          <div class="spinner"></div>
          <p>🧠 RAG 检索中 + LLM 生成中...</p>
        </div>

        <div v-if="answer" class="card">
          <h3>📝 答案</h3>
          <div class="answer-text">{{ answer }}</div>
        </div>

        <div v-if="sources.length" class="card sources-card">
          <h3>🔗 来源溯源 ({{ sources.length }})</h3>
          <div v-for="(s, i) in sources" :key="i" class="source-item">
            <span class="source-num">[{{ i + 1 }}]</span>
            <div class="source-info">
              <div class="source-title">📄 {{ s.title || '未知文献' }}</div>
              <div class="source-page">第 {{ s.page || '?' }} 页</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const question = ref('')
const mode = ref('single')
const answer = ref('')
const sources = ref([])
const loading = ref(false)
const papers = ref([])
const paperId = ref('')

const currentPaperTitle = computed(
  () => papers.value.find((p) => p.paper_id === paperId.value)?.title || paperId.value,
)

const loadPapers = async () => {
  try {
    const r = await axios.get('/api/papers/')
    papers.value = r.data.papers || []
  } catch {
    papers.value = []
  }
}

onMounted(loadPapers)

const ask = async () => {
  if (!question.value.trim() || loading.value) return
  loading.value = true
  answer.value = ''
  sources.value = []
  try {
    const r = await axios.post('/api/qa/ask', {
      question: question.value,
      mode: mode.value,
      paper_id: mode.value === 'single' && paperId.value ? paperId.value : null,
    })
    answer.value = r.data.answer
    sources.value = r.data.sources || []
  } catch (e) {
    answer.value = '❌ 请求失败：' + e.message
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.qa-page { padding: 0; }
.page-title { font-size: 24px; margin-bottom: 4px; color: #1a1a2e; }
.subtitle { color: #888; margin-bottom: 20px; font-size: 13px; }

.qa-layout { display: grid; grid-template-columns: 1fr; gap: 20px; }

.card {
  background: #fff; border-radius: 10px; padding: 22px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06); margin-bottom: 16px;
}
.card h3 { margin: 0 0 14px 0; font-size: 16px; color: #1a1a2e; }

.textarea {
  width: 100%; padding: 12px 14px; border-radius: 8px;
  border: 1px solid #e0e0e0; font-size: 14px;
  resize: vertical; box-sizing: border-box; font-family: inherit;
  transition: border 0.2s;
}
.textarea:focus { outline: none; border-color: #4361ee; }

.controls {
  display: flex; justify-content: space-between; align-items: center;
  margin-top: 14px; flex-wrap: wrap; gap: 10px;
}
.mode-switch { display: flex; gap: 4px; background: #f0f2ff; padding: 4px; border-radius: 8px; }
.mode-btn {
  padding: 7px 14px; border: none; background: transparent;
  border-radius: 6px; cursor: pointer; font-size: 13px; color: #666;
  transition: all 0.2s;
}
.mode-btn.active { background: #4361ee; color: #fff; }

.paper-select {
  padding: 8px 12px; border-radius: 8px; border: 1px solid #e0e0e0;
  font-size: 13px; background: #fff; max-width: 320px; cursor: pointer;
}
.paper-select:focus { outline: none; border-color: #4361ee; }
.scope-tip {
  margin: 10px 0 0 0; font-size: 12px; color: #7b5b00;
  background: #fff8e1; border-left: 3px solid #f0b429;
  padding: 7px 10px; border-radius: 4px;
}

.btn { padding: 8px 20px; border-radius: 6px; border: none; cursor: pointer; font-size: 14px; }
.btn-primary { background: #4361ee; color: #fff; }
.btn-primary:hover:not(:disabled) { background: #3a56d4; }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }

.empty-card { text-align: center; color: #888; padding: 40px; }
.empty-card p { margin-bottom: 16px; }
.quick { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; }
.chip {
  background: #f0f2ff; border: 1px solid #4361ee; color: #4361ee;
  padding: 6px 14px; border-radius: 20px; font-size: 12px; cursor: pointer;
  transition: all 0.2s;
}
.chip:hover { background: #4361ee; color: #fff; }

.loading-card { text-align: center; padding: 40px; }
.spinner {
  width: 32px; height: 32px; border: 3px solid #e0e0e0;
  border-top-color: #4361ee; border-radius: 50%;
  animation: spin 0.8s linear infinite; margin: 0 auto 12px;
}
@keyframes spin { to { transform: rotate(360deg); } }

.answer-text {
  line-height: 1.8; font-size: 15px; color: #222;
  background: #f8f9ff; padding: 16px; border-radius: 8px;
  white-space: pre-wrap;
}

.sources-card h3 { color: #2e7d32; }
.source-item {
  display: flex; gap: 10px; padding: 10px 12px;
  background: #f1f8e9; border-radius: 8px; margin-bottom: 8px;
  border-left: 3px solid #7cb342;
}
.source-num {
  background: #7cb342; color: #fff; border-radius: 50%;
  width: 24px; height: 24px; display: flex; align-items: center;
  justify-content: center; font-size: 11px; font-weight: bold; flex-shrink: 0;
}
.source-title { font-size: 13px; font-weight: 500; color: #333; }
.source-page { font-size: 12px; color: #888; margin-top: 2px; }
</style>
