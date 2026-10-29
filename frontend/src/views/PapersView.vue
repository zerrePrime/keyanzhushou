<template>
  <div class="papers-page">
    <h1 class="page-title">📚 文献库管理</h1>
    <p class="subtitle">上传 PDF → 自动解析切块 → 入库 Chroma → 支持 RAG 问答</p>

    <div class="upload-card card">
      <h3>⬆️ 上传 PDF 论文</h3>
      <div
        class="drop-zone"
        :class="{ dragging }"
        @dragover.prevent="dragging = true"
        @dragleave.prevent="dragging = false"
        @drop.prevent="onDrop"
        @click="$refs.fileInput.click()"
      >
        <input
          ref="fileInput"
          type="file"
          accept=".pdf"
          multiple
          @change="onFileChange"
          style="display:none"
        />
        <div class="drop-icon">📄</div>
        <p><strong>点击或拖拽 PDF 文件到这里</strong></p>
        <p class="hint">支持批量上传，最大 100MB</p>
      </div>
      <div class="uploading-list" v-if="uploading">
        <div class="upload-item">
          <span>⏳ {{ uploadingName }} 上传中...</span>
          <div class="progress-bar"><div class="progress-fill" :style="{width: progress + '%'}"></div></div>
        </div>
      </div>
      <div class="upload-msg" :class="uploadMsgClass">
        {{ uploadMsg }}
      </div>
    </div>

    <div class="card">
      <div class="list-header">
        <h3>📋 文献列表 ({{ papers.length }})</h3>
        <span v-if="papers.length" class="summary">
          共 {{ totalChunks }} 个切块 · {{ totalPages }} 页
        </span>
      </div>

      <div v-if="papers.length === 0" class="empty">
        <div class="empty-icon">📚</div>
        <p>文献库为空，请上传第一篇 PDF 开始你的科研之旅</p>
      </div>

      <div v-else class="paper-list">
        <div v-for="p in papersGrouped" :key="p.paper_id" class="paper-item">
          <div class="paper-icon">📄</div>
          <div class="paper-info">
            <div class="paper-title">{{ p.title || '未知标题' }}</div>
            <div class="paper-meta">
              <code>{{ p.paper_id }}</code>
              <span v-if="p.page">· 切块含 p{{ p.page }}</span>
            </div>
          </div>
          <button class="del-btn" @click="del(p.paper_id)" title="删除">🗑️</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const papers = ref([])
const uploading = ref(false)
const uploadingName = ref('')
const progress = ref(0)
const uploadMsg = ref('')
const uploadMsgClass = ref('')
const dragging = ref(false)

// 把所有 chunks 按 paper_id 分组去重
const papersGrouped = computed(() => {
  const seen = {}
  for (const p of papers.value) {
    if (!seen[p.paper_id]) seen[p.paper_id] = { ...p, pages: new Set() }
    if (p.page !== undefined) seen[p.paper_id].pages.add(p.page)
  }
  return Object.values(seen).map((p) => ({
    ...p,
    pages: [...p.pages].sort(),
  }))
})
const totalChunks = computed(() => papers.value.length)
const totalPages = computed(() => {
  const set = new Set()
  papers.value.forEach((p) => p.page !== undefined && set.add(p.paper_id + '-' + p.page))
  return set.size
})

const loadPapers = async () => {
  try {
    const r = await axios.get('/api/papers/')
    papers.value = r.data.papers
  } catch (e) {
    console.error(e)
  }
}

const doUpload = async (file) => {
  uploading.value = true
  uploadingName.value = file.name
  uploadMsg.value = ''
  progress.value = 30

  const fd = new FormData()
  fd.append('file', file)

  try {
    const r = await axios.post('/api/papers/upload', fd)
    progress.value = 100
    const d = r.data

    // MD5 精确重复（直接拒绝）
    if (d.status === 'duplicate') {
      uploadMsg.value = `⛔ 上传失败：${d.message || '文件完全相同，已存在于库中'}`
      uploadMsgClass.value = 'error'
      return
    }

    // 语义级去重提示（高重合 / 版本演进）
    const dets = d.detections || []
    if (d.status === 'semantic_duplicate' && dets.length) {
      const top = dets[0]
      const iden = top.identical_chunks || '?'
      const total = top.total_chunks || '?'
      uploadMsg.value = `⚠️ 语义高度重合！与「${top.title}」相似度 ${(top.top1_mean * 100).toFixed(0)}%（${iden}/${total} 个 chunk 几乎相同）— 建议确认不要重复入库`
      uploadMsgClass.value = 'warn'
    } else if (d.status === 'version_warning' && dets.length) {
      const top = dets[0]
      uploadMsg.value = `🔍 疑似版本演进：与「${top.title}」相似度 ${(top.top1_mean * 100).toFixed(0)}%（如 arXiv v1→v7 修订版）— 建议保留最新版本`
      uploadMsgClass.value = 'warn'
    } else if (d.status === 'success') {
      uploadMsg.value = `✅ 成功入库！「${d.title}」— ${d.chunks_count} 切块, ${d.total_pages} 页`
      uploadMsgClass.value = 'success'
    } else {
      uploadMsg.value = `❌ 上传失败`
      uploadMsgClass.value = 'error'
    }

    // 同时展示所有检测到的重复项（最多 3 条）
    if (dets.length > 1) {
      uploadMsg.value += `\n└─ 还检测到 ${dets.length - 1} 篇相似论文`
    }
  } catch (e) {
    uploadMsg.value = `❌ 上传失败: ${e.message}`
    uploadMsgClass.value = 'error'
  } finally {
    uploading.value = false
    await loadPapers()
  }
}

const onFileChange = (e) => {
  for (const f of e.target.files) doUpload(f)
  e.target.value = ''
}

const onDrop = (e) => {
  dragging.value = false
  for (const f of e.dataTransfer.files) {
    if (f.name.toLowerCase().endsWith('.pdf')) doUpload(f)
  }
}

const del = async (id) => {
  if (!confirm('确定删除这篇论文及其所有切块吗？')) return
  try {
    await axios.delete(`/api/papers/${id}`)
    loadPapers()
  } catch (e) {
    alert('删除失败')
  }
}

onMounted(loadPapers)
</script>

<style scoped>
.papers-page { padding: 0; }
.page-title { font-size: 24px; margin-bottom: 4px; color: #1a1a2e; }
.subtitle { color: #888; margin-bottom: 20px; font-size: 13px; }

.card {
  background: #fff; border-radius: 10px; padding: 22px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.06); margin-bottom: 16px;
}
.card h3 { margin: 0 0 14px 0; font-size: 16px; color: #1a1a2e; }

.upload-card h3 { margin-bottom: 18px; }

.drop-zone {
  border: 2px dashed #ddd; border-radius: 12px; padding: 36px;
  text-align: center; cursor: pointer; transition: all 0.2s;
  background: #fafbff;
}
.drop-zone:hover, .drop-zone.dragging {
  border-color: #4361ee; background: #eef1ff;
}
.drop-icon { font-size: 48px; margin-bottom: 10px; }
.drop-zone p { margin: 4px 0; }
.drop-zone .hint { color: #aaa; font-size: 12px; }

.uploading-list { margin-top: 14px; }
.upload-item { background: #f8f9ff; padding: 12px; border-radius: 8px; }
.progress-bar {
  height: 6px; background: #e0e0e0; border-radius: 3px; margin-top: 8px; overflow: hidden;
}
.progress-fill {
  height: 100%; background: linear-gradient(90deg, #4361ee, #7209b7);
  transition: width 0.3s;
}

.upload-msg {
  margin-top: 14px; padding: 12px 14px; border-radius: 8px;
  font-size: 13px; line-height: 1.5;
}
.upload-msg.success { background: #e8f5e9; color: #2e7d32; }
.upload-msg.warn    { background: #fff8e1; color: #f57c00; white-space: pre-line; }
.upload-msg.error   { background: #ffebee; color: #c62828; }

.list-header { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 14px; }
.summary { font-size: 12px; color: #888; }

.empty { text-align: center; padding: 40px; color: #aaa; }
.empty-icon { font-size: 48px; margin-bottom: 10px; }

.paper-list { display: flex; flex-direction: column; gap: 8px; }
.paper-item {
  display: flex; gap: 14px; align-items: center;
  padding: 14px 16px; background: #f8f9ff; border-radius: 10px;
  transition: all 0.2s; border-left: 3px solid #4361ee;
}
.paper-item:hover { background: #eef1ff; transform: translateX(3px); }
.paper-icon { font-size: 28px; }
.paper-info { flex: 1; min-width: 0; }
.paper-title { font-size: 14px; font-weight: 500; color: #1a1a2e; margin-bottom: 4px; }
.paper-meta { font-size: 12px; color: #888; display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
code {
  background: #f4f4f4; padding: 2px 6px; border-radius: 3px;
  font-size: 11px; font-family: monospace;
}
.del-btn {
  background: transparent; border: none; font-size: 18px;
  cursor: pointer; padding: 6px; opacity: 0.5; transition: all 0.2s;
}
.del-btn:hover { opacity: 1; transform: scale(1.2); }
</style>
