import { createApp } from 'vue'
import axios from 'axios'
import App from './App.vue'
import router from './router'
import './style.css'

// 会话过期时统一跳登录页（登录相关接口除外，避免掩盖密码错误提示）
axios.interceptors.response.use(
  (res) => res,
  (err) => {
    const url = err?.config?.url || ''
    if (err?.response?.status === 401 && !url.includes('/api/auth/')) {
      if (window.location.pathname !== '/login') window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

const app = createApp(App)
app.use(router)
app.mount('#app')
