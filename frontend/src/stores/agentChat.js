// Agent 会话状态放在模块级：
// 路由切换只卸载组件、模块不会重新执行，所以对话记录保留；
// 刷新页面时模块重新加载，状态重置为空 —— 正好符合「刷新才清空」。
import { ref, computed } from 'vue'
import axios from 'axios'

export const messages = ref([])
export const input = ref('')
export const loading = ref(false)

export const toolCallCount = computed(() =>
  messages.value
    .filter((m) => m.role === 'assistant' && m.trace && m.trace.length)
    .reduce((sum, m) => sum + m.trace.filter((s) => s.tool !== 'FINISH').length, 0)
)

// 最近一次回答串联的工具链路，用于状态面板展示
export const lastChain = computed(() => {
  const last = [...messages.value].reverse().find((m) => m.role === 'assistant' && m.toolsUsed)
  return last ? last.toolsUsed : '—'
})

export function clearAll() {
  messages.value = []
}

export async function send(text) {
  // keydown.enter 会把 KeyboardEvent 当参数传进来，只接受字符串
  const content = (typeof text === 'string' ? text : input.value).trim()
  if (!content || loading.value) return

  messages.value.push({ role: 'user', content })
  input.value = ''
  loading.value = true

  try {
    const r = await axios.post('/api/agent/chat', { message: content })
    const trace = r.data.thinking_trace || []
    messages.value.push({
      role: 'assistant',
      content: r.data.answer,
      trace,
      traceOpen: false, // 默认折叠思考链，点击展开查看完整内容
      toolsUsed: (r.data.all_tools || []).join(' → '),
      tool_used: r.data.tool_used || '',
      sources: r.data.sources || [],
    })
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content: '❌ Agent 请求失败: ' + e.message,
    })
  } finally {
    loading.value = false
  }
}
