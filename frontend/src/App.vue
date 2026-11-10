<template>
  <div id="app">
    <!-- 侧边栏（登录页隐藏） -->
    <nav v-if="!isAuthPage" class="sidebar">
      <div class="logo">
        <div class="logo-icon">🧠</div>
        <div class="logo-text">
          <div class="logo-title">Research Agent</div>
          <div class="logo-sub">AI 科研助手</div>
        </div>
      </div>

      <router-link to="/papers" class="nav-item" active-class="active">
<span>文献库</span>
      </router-link>
      <router-link to="/qa" class="nav-item" active-class="active">
<span>RAG 问答</span>
      </router-link>
      <router-link to="/agent" class="nav-item" active-class="active">
<span>Agent 对话</span>
      </router-link>
      <router-link to="/arxiv" class="nav-item" active-class="active">
<span>arXiv 检索</span>
      </router-link>
      <router-link to="/graph" class="nav-item" active-class="active">
<span>引用图谱</span>
      </router-link>
      <router-link to="/writing" class="nav-item" active-class="active">
<span>写作 Copilot</span>
      </router-link>
      <router-link to="/reader" class="nav-item" active-class="active">
<span>PDF 阅读</span>
      </router-link>

      <div class="sidebar-footer">
        <div class="status" :class="backendOnline ? 'online' : 'offline'">
          <span class="dot"></span>
          {{ backendOnline ? '后端在线' : '后端离线' }}
        </div>
        <button class="logout" @click="logout">退出登录</button>
      </div>
    </nav>

    <!-- 主内容区 -->
    <main class="content" :class="{ 'content-auth': isAuthPage }">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'

const route = useRoute()
const isAuthPage = computed(() => route.path === '/login')

const backendOnline = ref(false)
let pollTimer = null

const checkBackend = async () => {
  try {
    await axios.get('/health', { timeout: 2000 })
    backendOnline.value = true
  } catch {
    backendOnline.value = false
  }
}

const logout = async () => {
  try {
    await axios.post('/api/auth/logout')
  } catch {
    // 忽略失败，直接回登录页
  }
  window.location.href = '/login'
}

onMounted(() => {
  if (isAuthPage.value) return
  checkBackend()
  pollTimer = setInterval(checkBackend, 15000)
})
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
#app {
  display: flex; height: 100vh;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.sidebar {
  width: 220px; background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
  color: #fff; display: flex; flex-direction: column; padding: 16px 0;
  flex-shrink: 0; box-shadow: 2px 0 12px rgba(0, 0, 0, 0.15);
}

.logo {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 20px 20px; border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  margin-bottom: 8px;
}
.logo-icon { font-size: 28px; }
.logo-title { font-size: 16px; font-weight: 700; letter-spacing: 0.5px; }
.logo-sub { font-size: 11px; color: #8892b0; margin-top: 2px; }

.nav-item {
  display: flex; align-items: center; gap: 12px;
  padding: 11px 20px; color: #a0aec0; text-decoration: none;
  margin: 2px 10px; border-radius: 8px;
  transition: all 0.2s ease; font-size: 14px; position: relative;
}
.nav-item:hover { background: rgba(67, 97, 238, 0.15); color: #fff; }
.nav-item.active {
  background: linear-gradient(135deg, #4361ee, #3a56d4);
  color: #fff; box-shadow: 0 4px 12px rgba(67, 97, 238, 0.4);
}
.nav-icon { font-size: 16px; width: 22px; text-align: center; }

.nav-badge {
  margin-left: auto; font-size: 10px; background: #ffd60a; color: #1a1a2e;
  padding: 2px 6px; border-radius: 4px; font-weight: bold;
}

.sidebar-footer {
  margin-top: auto; padding: 16px 20px; border-top: 1px solid rgba(255, 255, 255, 0.08);
}
.status {
  display: flex; align-items: center; gap: 8px; font-size: 12px;
  padding: 8px 12px; border-radius: 6px; background: rgba(255, 255, 255, 0.05);
}
.dot { width: 8px; height: 8px; border-radius: 50%; }
.status.online { color: #4ade80; }
.status.online .dot { background: #4ade80; box-shadow: 0 0 8px #4ade80; }
.status.offline { color: #f87171; }
.status.offline .dot { background: #f87171; }

.logout {
  width: 100%;
  margin-top: 10px;
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: transparent;
  color: #8892b0;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
  font-family: inherit;
}
.logout:hover {
  background: rgba(248, 113, 113, 0.12);
  border-color: rgba(248, 113, 113, 0.35);
  color: #ff9a9a;
}

.content.content-auth { padding: 0; background: #0f1222; overflow: hidden; }

.content {
  flex: 1; overflow-y: auto; padding: 28px 32px;
  background: #f5f7fa;
}

/* 路由过渡 */
.fade-enter-active, .fade-leave-active { transition: opacity 0.15s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
