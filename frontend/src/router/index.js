import { createRouter, createWebHistory } from 'vue-router'
import axios from 'axios'

const routes = [
  { path: '/login', component: () => import('../views/LoginView.vue'), meta: { public: true } },
  { path: '/', redirect: '/papers' },
  { path: '/papers', component: () => import('../views/PapersView.vue') },
  { path: '/qa', component: () => import('../views/QAView.vue') },
  { path: '/agent', component: () => import('../views/AgentView.vue') },
  { path: '/arxiv', component: () => import('../views/ArxivView.vue') },
  { path: '/graph', component: () => import('../views/GraphView.vue') },
  { path: '/writing', component: () => import('../views/WritingView.vue') },
  { path: '/reader', component: () => import('../views/ReaderView.vue') },
]

const router = createRouter({ history: createWebHistory(), routes })

// 会话校验只做一次，避免每次切路由都请求 /api/auth/me
let authChecked = false

router.beforeEach(async (to) => {
  if (to.meta.public) return true
  if (authChecked) return true
  try {
    await axios.get('/api/auth/me', { timeout: 5000 })
    authChecked = true
    return true
  } catch {
    authChecked = false
    return {
      path: '/login',
      query: to.fullPath === '/' ? {} : { redirect: to.fullPath },
    }
  }
})

export default router
