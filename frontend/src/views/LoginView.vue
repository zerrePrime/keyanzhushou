<template>
  <div class="login-wrap">
    <div class="orb orb-1"></div>
    <div class="orb orb-2"></div>
    <div class="grid-overlay"></div>

    <div class="card">
      <div class="brand">
        <div class="brand-icon">🧠</div>
        <h1>Research Agent</h1>
        <p>AI 科研助手 · 全流程科研工作台</p>
      </div>

      <form class="form" @submit.prevent="submit">
        <label class="field">
          <span>用户名</span>
          <input
            v-model.trim="username"
            type="text"
            autocomplete="username"
            placeholder="请输入用户名"
            :disabled="loading"
          />
        </label>

        <label class="field">
          <span>密码</span>
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            placeholder="请输入密码"
            :disabled="loading"
          />
        </label>

        <transition name="err">
          <div v-if="error" class="error">{{ error }}</div>
        </transition>

        <button type="submit" :disabled="loading">
          <span v-if="!loading">登 录</span>
          <span v-else class="spinner"></span>
        </button>
      </form>

      <div class="foot">文献解析 · RAG 溯源 · Agent 编排 · 学术写作</div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import axios from 'axios'

const router = useRouter()
const route = useRoute()

const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function submit() {
  if (!username.value || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await axios.post('/api/auth/login', {
      username: username.value,
      password: password.value,
    })
    const redirect =
      typeof route.query.redirect === 'string' ? route.query.redirect : '/papers'
    router.replace(redirect)
  } catch (e) {
    error.value = e?.response?.data?.detail || '登录失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: radial-gradient(1200px 600px at 20% 10%, #1b2350 0%, transparent 60%),
    radial-gradient(900px 500px at 85% 85%, #12303f 0%, transparent 60%), #0f1222;
  overflow: hidden;
}

/* 背景光斑 */
.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(90px);
  opacity: 0.45;
  pointer-events: none;
}
.orb-1 {
  width: 420px;
  height: 420px;
  background: #4361ee;
  top: -120px;
  left: -80px;
  animation: float 14s ease-in-out infinite;
}
.orb-2 {
  width: 360px;
  height: 360px;
  background: #22d3ee;
  bottom: -140px;
  right: -60px;
  animation: float 18s ease-in-out infinite reverse;
}
@keyframes float {
  0%, 100% { transform: translate3d(0, 0, 0) scale(1); }
  50% { transform: translate3d(30px, -24px, 0) scale(1.08); }
}

/* 细网格 */
.grid-overlay {
  position: absolute;
  inset: 0;
  background-image: linear-gradient(rgba(255, 255, 255, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.035) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(circle at 50% 45%, #000 0%, transparent 72%);
  -webkit-mask-image: radial-gradient(circle at 50% 45%, #000 0%, transparent 72%);
  pointer-events: none;
}

/* 卡片 */
.card {
  position: relative;
  z-index: 1;
  width: 380px;
  padding: 40px 36px 28px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.055);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: 0 24px 64px rgba(0, 0, 0, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  animation: rise 0.5s cubic-bezier(0.22, 1, 0.36, 1);
}
@keyframes rise {
  from { opacity: 0; transform: translateY(16px) scale(0.985); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}

.brand { text-align: center; margin-bottom: 30px; }
.brand-icon {
  width: 58px;
  height: 58px;
  margin: 0 auto 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(67, 97, 238, 0.35), rgba(34, 211, 238, 0.2));
  border: 1px solid rgba(255, 255, 255, 0.14);
  box-shadow: 0 8px 24px rgba(67, 97, 238, 0.35);
}
.brand h1 {
  margin: 0;
  font-size: 21px;
  font-weight: 700;
  letter-spacing: 0.6px;
  color: #fff;
}
.brand p {
  margin: 7px 0 0;
  font-size: 12px;
  color: #8892b0;
  letter-spacing: 0.3px;
}

.form { display: flex; flex-direction: column; gap: 16px; }

.field { display: flex; flex-direction: column; gap: 7px; }
.field span {
  font-size: 12px;
  color: #9aa5c0;
  letter-spacing: 0.4px;
}
.field input {
  height: 42px;
  padding: 0 14px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(10, 14, 30, 0.55);
  color: #f0f3fa;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s, box-shadow 0.2s, background 0.2s;
}
.field input::placeholder { color: #5a6480; }
.field input:hover { border-color: rgba(255, 255, 255, 0.2); }
.field input:focus {
  border-color: #4361ee;
  background: rgba(10, 14, 30, 0.75);
  box-shadow: 0 0 0 3px rgba(67, 97, 238, 0.22);
}
.field input:disabled { opacity: 0.6; cursor: not-allowed; }

.error {
  font-size: 12.5px;
  color: #ff8a8a;
  background: rgba(248, 113, 113, 0.1);
  border: 1px solid rgba(248, 113, 113, 0.25);
  padding: 8px 12px;
  border-radius: 8px;
  animation: shake 0.3s ease;
}
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-4px); }
  75% { transform: translateX(4px); }
}
.err-enter-active, .err-leave-active { transition: opacity 0.18s, transform 0.18s; }
.err-enter-from, .err-leave-to { opacity: 0; transform: translateY(-4px); }

button {
  height: 44px;
  margin-top: 6px;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, #4361ee, #3a56d4);
  color: #fff;
  font-size: 14.5px;
  font-weight: 600;
  letter-spacing: 3px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 22px rgba(67, 97, 238, 0.38);
  transition: transform 0.16s, box-shadow 0.16s, filter 0.16s;
}
button:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 12px 28px rgba(67, 97, 238, 0.5);
  filter: brightness(1.06);
}
button:active:not(:disabled) { transform: translateY(0); }
button:disabled { cursor: not-allowed; filter: saturate(0.7) brightness(0.9); }

.spinner {
  width: 17px;
  height: 17px;
  border: 2px solid rgba(255, 255, 255, 0.32);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.foot {
  margin-top: 26px;
  padding-top: 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.07);
  text-align: center;
  font-size: 11px;
  color: #5f6a86;
  letter-spacing: 0.6px;
}
</style>
