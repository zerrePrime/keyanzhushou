import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/papers' },
  { path: '/papers', component: () => import('../views/PapersView.vue') },
  { path: '/qa', component: () => import('../views/QAView.vue') },
  { path: '/agent', component: () => import('../views/AgentView.vue') },
  { path: '/arxiv', component: () => import('../views/ArxivView.vue') },
  { path: '/graph', component: () => import('../views/GraphView.vue') },
  { path: '/writing', component: () => import('../views/WritingView.vue') },
  { path: '/reader', component: () => import('../views/ReaderView.vue') },
]

export default createRouter({ history: createWebHistory(), routes })
