<template>
  <div class="agent-page">
    <h1 class="page-title">🤖 Agent 对话（LangGraph）</h1>
    <p class="subtitle">Agent 自主决策 → 选择工具 → 执行 → 汇总回答</p>

    <div class="agent-layout">
      <!-- 左侧：对话区 -->
      <div class="chat-panel">
        <div ref="messagesRef" class="messages">
          <!-- 欢迎消息 -->
          <div class="msg assistant">
            <div class="avatar">🤖</div>
            <div class="bubble">
              <p>你好！我是 LangGraph 驱动的科研助手 Agent。</p>
              <p>我有以下能力，你可以随便问：</p>
              <div class="quick-actions">
                <button class="chip" @click="send('文献库有什么论文？')">📚 列出文献库</button>
                <button class="chip" @click="send('帮我分析引用图谱的基石论文')">🕸️ 基石论文</button>
                <button class="chip" @click="send('我想做一个用 RAG 改进 Agent 的研究，帮我搭论文框架')">✍️ 搭框架</button>
                <button class="chip" @click="send('最近 RAG Agent 有什么新进展？')">🔎 查 arXiv</button>
              </div>
            </div>
          </div>

          <!-- 历史消息 -->
          <div
            v-for="(msg, i) in messages"
            :key="i"
            class="msg"
            :class="msg.role"
          >
            <div class="avatar">{{ msg.role === 'user' ? '👤' : '🤖' }}</div>
            <div class="bubble">
              <!-- Agent 思考链（多步决策时间线） -->
              <div class="trace" v-if="msg.trace && msg.trace.length">
                <div class="trace-head" @click="msg.traceOpen = !msg.traceOpen">
                  <span class="trace-title">🧠 Agent 思考链 · {{ msg.trace.filter(s => s.tool !== 'FINISH' && s.tool !== 'DIRECT').length }} 步</span>
                  <span class="trace-toggle">{{ msg.traceOpen ? '收起 ▴' : '展开 ▾' }}</span>
                </div>
                <div class="trace-body" v-show="msg.traceOpen">
                  <div
                    v-for="(s, k) in msg.trace"
                    :key="k"
                    class="trace-step"
                    :class="[s.status, { finish: s.tool === 'FINISH' }]"
                  >
                    <div class="step-top">
                      <span class="step-badge">{{ s.step }}</span>
                      <span class="step-tool">{{ s.tool }}</span>
                      <span class="step-time" v-if="s.elapsed_ms > 0">{{ (s.elapsed_ms / 1000).toFixed(2) }}s</span>
                    </div>
                    <div class="step-intent">💭 {{ s.intent }}</div>
                    <div class="step-query" v-if="s.query">→ {{ s.query }}</div>
                    <div class="step-out" v-if="s.output_summary">📥 {{ s.output_full || s.output_summary }}</div>
                  </div>
                  <div class="trace-end">✨ 汇总生成最终回答</div>
                </div>
              </div>
              <div class="answer">{{ msg.content }}</div>
              <div class="sources" v-if="msg.sources && msg.sources.length">
                <div v-for="(s, j) in msg.sources" :key="j" class="source-tag">
                  📄 {{ s.title || '文献' }} p{{ s.page || '?' }}
                </div>
              </div>
            </div>
          </div>

          <!-- 加载中 -->
          <div v-if="loading" class="msg assistant">
            <div class="avatar">🤖</div>
            <div class="bubble">
              <div class="thinking">
                <span class="thinking-label">🧠 Agent 正在多步规划（最多 3 步工具串联）</span>
                <span class="thinking-tool">
                  <span class="dots"></span>
                </span>
              </div>
            </div>
          </div>
        </div>

        <!-- 输入区 -->
        <div class="input-area">
          <textarea
            v-model="input"
            @keydown.enter.exact.prevent="send"
            placeholder="问我任何科研相关的问题..."
            rows="2"
            :disabled="loading"
          ></textarea>
          <button class="send-btn" @click="send" :disabled="!input.trim() || loading">
            {{ loading ? '...' : '🚀' }}
          </button>
        </div>
      </div>

      <!-- 右侧：工具面板 -->
      <div class="tools-panel">
        <div class="card">
          <h3>🛠️ Agent 可用工具 ({{ tools.length }})</h3>
          <div v-if="tools.length === 0" class="empty">加载中...</div>
          <div v-for="(t, i) in tools" :key="i" class="tool-item">
            <div class="tool-name">{{ t.name }}</div>
            <div class="tool-desc">{{ t.description }}</div>
          </div>
        </div>

        <div class="card">
          <h3>📊 当前状态</h3>
          <div class="status-item">
            <span>LangGraph 状态机</span>
            <span class="status-ok">✓ 就绪</span>
          </div>
          <div class="status-item">
            <span>已调用工具</span>
            <span class="status-num">{{ toolCallCount }}</span>
          </div>
          <div class="status-item">
            <span>最近串联链路</span>
            <span class="status-chain">{{ lastChain }}</span>
          </div>
          <div class="status-item">
            <span>对话轮数</span>
            <span class="status-num">{{ messages.filter(m => m.role === 'user').length }}</span>
          </div>
        </div>

        <div class="card" style="text-align:center">
          <button class="btn btn-secondary" @click="clearAll">🗑️ 清空对话</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick, watch } from 'vue'
import axios from 'axios'
import {
  messages,
  input,
  loading,
  toolCallCount,
  lastChain,
  send,
  clearAll,
} from '../stores/agentChat'

const tools = ref([])
const messagesRef = ref(null)

const scrollBottom = async () => {
  await nextTick()
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

// 会话状态已提到模块级，组件不再直接操作消息数组，改为监听变化后滚动到底部
watch([() => messages.value.length, loading], () => {
  scrollBottom()
})

const loadTools = async () => {
  try {
    const r = await axios.get('/api/agent/tools')
    tools.value = r.data.tools
  } catch {
    // Agent 路由还没注册好时的兜底
    tools.value = [
      { name: 'rag_qa', description: '文献库 RAG 问答' },
      { name: 'arxiv_search', description: 'arXiv 检索' },
      { name: 'graph_analyze', description: '引用图谱分析' },
      { name: 'auto_survey', description: '自动综述' },
      { name: 'write_framework', description: '论文框架生成' },
      { name: 'list_papers', description: '列出文献' },
    ]
  }
}

onMounted(loadTools)
</script>

<style scoped>
.agent-page { padding: 0; height: calc(100vh - 56px); }
.page-title { font-size: 24px; margin-bottom: 4px; color: #1a1a2e; }
.subtitle { color: #888; margin-bottom: 16px; font-size: 13px; }

.agent-layout {
  display: grid; grid-template-columns: 1fr 300px;
  gap: 20px; height: calc(100% - 60px);
}
@media (max-width: 900px) { .agent-layout { grid-template-columns: 1fr; } }

/* 对话面板 */
.chat-panel {
  background: #fff; border-radius: 12px; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06);
  display: flex; flex-direction: column; overflow: hidden;
}
.messages {
  flex: 1; overflow-y: auto; padding: 24px;
  display: flex; flex-direction: column; gap: 20px;
}

.msg { display: flex; gap: 12px; max-width: 85%; }
.msg.user { align-self: flex-end; flex-direction: row-reverse; }
.msg.assistant { align-self: flex-start; }

.avatar {
  width: 36px; height: 36px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px; flex-shrink: 0;
}
.msg.user .avatar { background: #4361ee; }
.msg.assistant .avatar { background: #f0f2ff; }

.bubble {
  background: #f8f9ff; border-radius: 12px; padding: 14px 18px;
  line-height: 1.7; font-size: 14px; color: #333;
}
.msg.user .bubble { background: #4361ee; color: #fff; }

.bubble p { margin: 0 0 8px 0; }
.bubble p:last-child { margin-bottom: 0; }

.quick-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.chip {
  background: #fff; border: 1px solid #4361ee; color: #4361ee;
  padding: 6px 12px; border-radius: 20px; font-size: 12px;
  cursor: pointer; transition: all 0.2s;
}
.chip:hover { background: #4361ee; color: #fff; }

.thinking {
  background: #fff8e1; border-left: 3px solid #ffd60a;
  padding: 8px 12px; border-radius: 6px; margin-bottom: 10px;
  display: flex; gap: 10px; align-items: center; font-size: 12px;
}
.thinking-label { color: #888; }
.thinking-tool { color: #e65100; font-family: monospace; font-weight: bold; }

/* Agent 思考链时间线 */
.trace {
  background: #fffdf5; border: 1px solid #ffe9a8; border-radius: 8px;
  margin-bottom: 12px; overflow: hidden; font-size: 12px;
}
.trace-head {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 12px; cursor: pointer; user-select: none;
  background: #fff8e1; border-bottom: 1px solid #ffe9a8;
}
.trace-title { color: #b26a00; font-weight: 600; }
.trace-toggle { color: #999; font-size: 11px; }
.trace-body { padding: 10px 12px 12px; display: flex; flex-direction: column; gap: 12px; }

.trace-step {
  position: relative; padding-left: 26px;
  border-left: 2px solid #ffe9a8; margin-left: 6px;
}
.trace-step.finish { border-left-color: #a5d6a7; }
.step-top { display: flex; align-items: center; gap: 8px; }
.step-badge {
  position: absolute; left: -9px; top: 0;
  width: 16px; height: 16px; border-radius: 50%;
  background: #ffd60a; color: #7a4a00; font-size: 10px; font-weight: bold;
  display: flex; align-items: center; justify-content: center;
}
.trace-step.finish .step-badge { background: #a5d6a7; color: #1b5e20; }
.trace-step.error .step-badge { background: #ef9a9a; color: #b71c1c; }
.step-tool { font-family: monospace; font-weight: bold; color: #e65100; font-size: 12px; }
.trace-step.finish .step-tool { color: #2e7d32; }
.step-time { margin-left: auto; color: #aaa; font-size: 11px; font-family: monospace; }
.step-intent { color: #555; margin-top: 3px; line-height: 1.5; }
.step-query {
  margin-top: 4px; color: #4361ee; font-family: monospace; font-size: 11px;
  background: #f0f2ff; padding: 2px 6px; border-radius: 4px;
  display: inline-block; word-break: break-all;
}
.step-out { margin-top: 4px; color: #666; line-height: 1.5; word-break: break-all; }
.trace-end { color: #2e7d32; font-size: 11px; padding-left: 6px; }

.status-chain {
  font-family: monospace; color: #7209b7; font-weight: bold;
  font-size: 11px; max-width: 160px; text-align: right;
}

.dots { display: inline-block; width: 40px; text-align: left; }
.dots::after {
  content: ''; animation: dots 1.5s steps(4, end) infinite;
}
@keyframes dots {
  0%, 20% { content: ''; }
  40% { content: '.'; }
  60% { content: '..'; }
  80%, 100% { content: '...'; }
}

.sources { margin-top: 10px; display: flex; gap: 6px; flex-wrap: wrap; }
.source-tag {
  background: #e8f5e9; color: #2e7d32; font-size: 11px;
  padding: 3px 8px; border-radius: 10px;
}

/* 输入区 */
.input-area {
  display: flex; gap: 10px; padding: 16px; border-top: 1px solid #eee;
  background: #fafafa;
}
.input-area textarea {
  flex: 1; padding: 12px; border-radius: 10px; border: 1px solid #ddd;
  font-size: 14px; resize: none; font-family: inherit;
}
.input-area textarea:focus { outline: none; border-color: #4361ee; }
.send-btn {
  width: 50px; border-radius: 10px; border: none;
  background: linear-gradient(135deg, #4361ee, #7209b7);
  color: #fff; font-size: 18px; cursor: pointer; transition: transform 0.2s;
}
.send-btn:hover:not(:disabled) { transform: scale(1.05); }
.send-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* 工具面板 */
.tools-panel { display: flex; flex-direction: column; overflow-y: auto; }
.card {
  background: #fff; border-radius: 10px; padding: 18px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06); margin-bottom: 16px;
}
.card h3 { margin: 0 0 14px 0; font-size: 15px; color: #1a1a2e; }

.tool-item {
  padding: 10px 12px; background: #f8f9ff; border-radius: 8px;
  margin-bottom: 8px; border-left: 3px solid #4361ee;
}
.tool-name { font-family: monospace; font-weight: bold; color: #4361ee; font-size: 13px; }
.tool-desc { font-size: 12px; color: #666; margin-top: 3px; line-height: 1.5; }

.status-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 0; font-size: 13px; border-bottom: 1px solid #f0f0f0;
}
.status-item:last-child { border-bottom: none; }
.status-ok { color: #4ade80; font-weight: bold; }
.status-num { font-family: monospace; color: #4361ee; font-weight: bold; }

.empty { color: #aaa; font-size: 13px; text-align: center; padding: 20px; }

.btn { padding: 8px 18px; border-radius: 6px; border: none; cursor: pointer; font-size: 14px; }
.btn-secondary { background: #6c757d; color: #fff; }
.btn-secondary:hover { background: #5a6268; }
</style>
