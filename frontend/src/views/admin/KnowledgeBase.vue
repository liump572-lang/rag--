<template>
  <div class="knowledge-base">
    <el-card>
      <div class="page-header">
        <h2>知识库管理</h2>
        <el-button type="primary" @click="showUpload">上传文档</el-button>
      </div>

      <!-- 状态统计卡片 -->
      <div class="stat-cards">
        <div class="stat"><span class="num">{{ stats.parsed }}</span><span class="label">已解析</span></div>
        <div class="stat warn"><span class="num">{{ stats.parsing }}</span><span class="label">解析中</span></div>
        <div class="stat warn"><span class="num">{{ stats.building }}</span><span class="label">图谱构建中</span></div>
        <div class="stat ok"><span class="num">{{ stats.graphDone }}</span><span class="label">图谱完成</span></div>
        <div class="stat danger"><span class="num">{{ stats.parseFailed }}</span><span class="label">解析失败</span></div>
        <div class="stat danger"><span class="num">{{ stats.graphFailed }}</span><span class="label">图谱失败</span></div>
        <div class="stat-hint" v-if="hasActive">
          <span class="dot" /> 后台处理中，列表每 3 秒自动刷新
        </div>
      </div>

      <el-form :model="filter" inline class="filter-bar">
        <el-form-item label="科目">
          <el-select v-model="filter.subject_id" placeholder="全部" clearable style="width:140px">
            <el-option v-for="s in subjects" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="filter.doc_type" placeholder="全部" clearable style="width:120px">
            <el-option label="教材" value="textbook" />
            <el-option label="真题" value="exam" />
            <el-option label="笔记" value="note" />
            <el-option label="补充" value="supplement" />
          </el-select>
        </el-form-item>
        <el-form-item label="解析状态">
          <el-select v-model="filter.parse_status" placeholder="全部" clearable style="width:120px">
            <el-option label="等待中" value="pending" />
            <el-option label="解析中" value="parsing" />
            <el-option label="成功" value="success" />
            <el-option label="失败" value="failed" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-input v-model="filter.keyword" placeholder="搜索文档标题" clearable style="width:200px" @keyup.enter="onSearch" />
        </el-form-item>
        <el-form-item>
          <el-button @click="onSearch">查询</el-button>
        </el-form-item>
      </el-form>

      <el-table :data="documents" stripe v-loading="loading" style="width: 100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
        <el-table-column prop="subject_name" label="科目" width="110" />
        <el-table-column prop="file_type" label="格式" width="70">
          <template #default="{ row }">
            <el-tag size="small">{{ row.file_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="doc_type" label="类型" width="80">
          <template #default="{ row }">
            <el-tag :type="docTypeTag(row.doc_type)" size="small">{{ docTypeLabel(row.doc_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="文档解析" width="100">
          <template #default="{ row }">
            <el-tag :type="parseTag(row.parse_status)" size="small" :title="row.error_msg || ''">
              {{ parseLabel(row.parse_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="图谱构建" width="130">
          <template #default="{ row }">
            <el-tag :type="graphTag(row)" size="small" :title="row.graph_error || ''">{{ graphLabel(row) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="chunk_count" label="片段数" width="70" />
        <el-table-column prop="created_at" label="上传时间" width="160" />
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="viewChunks(row)">片段</el-button>
            <el-button size="small" @click="handleReparse(row)">重新解析</el-button>
            <el-popconfirm title="确认删除该文档？" @confirm="handleDelete(row)">
              <template #reference>
                <el-button size="small" type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          :page-size="size"
          :total="total"
          layout="prev, pager, next"
          @current-change="() => fetchDocs()"
        />
      </div>
    </el-card>

    <el-dialog v-model="uploadVisible" title="上传文档" width="520px">
      <el-form ref="uploadFormRef" :model="uploadForm" :rules="uploadRules" label-width="80px">
        <el-form-item label="科目" prop="subject_id">
          <div style="display:flex;gap:6px">
            <el-select v-model="uploadForm.subject_id" placeholder="请选择科目" style="flex:1">
              <el-option v-for="s in subjects" :key="s.id" :label="s.name" :value="s.id" />
            </el-select>
            <el-button type="primary" :icon="Plus" @click="handleAddSubject" />
          </div>
        </el-form-item>
        <el-form-item label="标题" prop="title">
          <el-input v-model="uploadForm.title" />
        </el-form-item>
        <el-form-item label="类型" prop="doc_type">
          <el-select v-model="uploadForm.doc_type" style="width:100%">
            <el-option label="教材" value="textbook" />
            <el-option label="真题" value="exam" />
            <el-option label="笔记" value="note" />
            <el-option label="补充" value="supplement" />
          </el-select>
        </el-form-item>
        <el-form-item label="年份" prop="year" v-if="uploadForm.doc_type === 'exam'">
          <el-input-number v-model="uploadForm.year" :min="2000" :max="2030" />
        </el-form-item>
        <el-form-item label="题型" prop="question_type" v-if="uploadForm.doc_type === 'exam'">
          <el-input v-model="uploadForm.question_type" placeholder="如：选择题、填空题" />
        </el-form-item>
        <el-form-item label="文件" prop="file">
          <el-upload
            ref="fileUploadRef"
            :auto-upload="false"
            :limit="1"
            accept=".pdf,.docx,.pptx,.txt,.md"
            :on-change="onFileChange"
          >
            <el-button type="primary">选择文件</el-button>
            <template #tip>
              <span style="font-size:12px;color:#909399">支持 pdf/docx/pptx/txt/md</span>
            </template>
          </el-upload>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="handleUpload">上传</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="chunkVisible" title="文档片段" width="700px">
      <div v-loading="chunkLoading">
        <div v-for="c in chunks" :key="c.id" class="chunk-item">
          <div class="chunk-header">片段 #{{ c.chunk_index }} ({{ c.char_count }} 字符)</div>
          <div class="chunk-content">{{ c.content }}</div>
        </div>
        <el-empty v-if="!chunks.length" description="暂无片段" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, reactive, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { getDocumentList, uploadDocument, deleteDocument, reparseDocument, getDocumentChunks } from '@/api/kb'
import { getSubjects, createSubject } from '@/api/subjects'

const documents = ref([])
const subjects = ref([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const size = ref(20)

const filter = reactive({
  subject_id: null,
  doc_type: null,
  parse_status: null,
  keyword: '',
})

const uploadVisible = ref(false)
const uploading = ref(false)
const uploadFormRef = ref(null)
const selectedFile = ref(null)
const fileUploadRef = ref(null)

const uploadForm = reactive({
  subject_id: null,
  title: '',
  doc_type: 'textbook',
  year: null,
  question_type: '',
})

const uploadRules = {
  subject_id: [{ required: true, message: '请选择科目', trigger: 'change' }],
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
  doc_type: [{ required: true, message: '请选择类型', trigger: 'change' }],
}

const chunkVisible = ref(false)
const chunks = ref([])
const chunkLoading = ref(false)

const docTypeMap = { textbook: '教材', exam: '真题', note: '笔记', supplement: '补充' }
const parseMap = { pending: '等待中', parsing: '解析中', success: '成功', failed: '失败' }

function docTypeLabel(v) { return docTypeMap[v] || v }
function docTypeTag(v) { return v === 'exam' ? 'warning' : v === 'textbook' ? 'primary' : 'info' }

// ── 文档解析状态 ──
function parseLabel(v) { return parseMap[v] || v }
function parseTag(v) { return v === 'success' ? 'success' : v === 'failed' ? 'danger' : v === 'parsing' ? 'warning' : 'info' }

// ── 图谱构建状态（来自最新一次非 rebuild 抽取运行） ──
function graphPct(row) {
  if (row.graph_status === 'success') return 100
  const total = row.graph_total || 0
  const proc = row.graph_processed || 0
  return total > 0 ? Math.round((proc / total) * 100) : 0
}
function graphLabel(row) {
  if (row.parse_status !== 'success') return '—'
  const s = row.graph_status
  if (!s) return '未开始'
  if (s === 'queued') return '排队中'
  if (s === 'running') return `构建中 ${graphPct(row)}%`
  if (s === 'success') return '已完成'
  if (s === 'failed') return '失败'
  if (s === 'canceled') return '已取消'
  return s
}
function graphTag(row) {
  if (row.parse_status !== 'success') return 'info'
  const s = row.graph_status
  if (s === 'success') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'running' || s === 'queued') return 'warning'
  return 'info'
}

// ── 统计卡片 ──
const stats = computed(() => {
  const d = documents.value
  return {
    parsed: d.filter(x => x.parse_status === 'success').length,
    parsing: d.filter(x => ['pending', 'parsing'].includes(x.parse_status)).length,
    building: d.filter(x => x.parse_status === 'success' && ['queued', 'running'].includes(x.graph_status)).length,
    graphDone: d.filter(x => x.graph_status === 'success').length,
    parseFailed: d.filter(x => x.parse_status === 'failed').length,
    graphFailed: d.filter(x => x.parse_status === 'success' && x.graph_status === 'failed').length,
  }
})

// 是否还有处于非终态、需要继续轮询刷新的文档
const hasActive = computed(() =>
  documents.value.some(x =>
    ['pending', 'parsing'].includes(x.parse_status) ||
    ['queued', 'running'].includes(x.graph_status),
  ),
)

// ── 动态刷新（轮询） ──
let pollTimer = null
function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(() => {
    if (hasActive.value) fetchDocs(true)
    else stopPolling()
  }, 3000)
}
function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

onMounted(() => {
  fetchDocs()
  fetchSubjects()
})
onUnmounted(stopPolling)

async function fetchDocs(silent = false) {
  if (!silent) loading.value = true
  try {
    const params = { page: page.value, size: size.value, ...filter }
    Object.keys(params).forEach(k => { if (params[k] === '' || params[k] === null) delete params[k] })
    const res = await getDocumentList(params)
    if (res.code === 200) {
      documents.value = res.data.items
      total.value = res.data.total
    }
  } finally {
    if (!silent) loading.value = false
    // 有进行中的文档则保持轮询，否则停止
    if (hasActive.value) startPolling()
    else stopPolling()
  }
}

function onSearch() {
  page.value = 1
  fetchDocs()
}

async function fetchSubjects() {
  try {
    const res = await getSubjects()
    if (res.code === 200) {
      subjects.value = res.data.map(s => ({ id: s.id, name: s.name }))
    }
  } catch {}
}

function showUpload() {
  uploadVisible.value = true
  uploadForm.subject_id = null
  uploadForm.title = ''
  uploadForm.doc_type = 'textbook'
  uploadForm.year = null
  uploadForm.question_type = ''
  selectedFile.value = null
}

async function handleAddSubject() {
  try {
    const { value } = await ElMessageBox.prompt('请输入新科目名称', '新增科目', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '科目名称不能为空',
    })
    if (!value?.trim()) return
    const res = await createSubject({ name: value.trim(), description: '' })
    if (res.code === 200) {
      ElMessage.success('科目创建成功')
      await fetchSubjects()
      uploadForm.subject_id = res.data.id
    } else {
      ElMessage.error(res.message || '创建失败')
    }
  } catch { }
}

function onFileChange(_, files) {
  if (files.length) {
    selectedFile.value = files[0].raw
  } else {
    selectedFile.value = null
  }
}

async function handleUpload() {
  const valid = await uploadFormRef.value.validate().catch(() => false)
  if (!valid) return
  if (!selectedFile.value) {
    ElMessage.warning('请选择文件')
    return
  }
  uploading.value = true
  try {
    const fd = new FormData()
    fd.append('subject_id', uploadForm.subject_id)
    fd.append('title', uploadForm.title)
    fd.append('doc_type', uploadForm.doc_type)
    if (uploadForm.year) fd.append('year', uploadForm.year)
    fd.append('question_type', uploadForm.question_type || '')
    fd.append('file', selectedFile.value)
    const res = await uploadDocument(fd)
    if (res.code === 200) {
      ElMessage.success('已开始上传，解析与图谱构建将在后台进行，列表自动刷新')
      uploadVisible.value = false
      page.value = 1
      fetchDocs()
    }
  } catch (e) {
    ElMessage.error(e.response?.data?.message || '上传失败')
  } finally {
    uploading.value = false
  }
}

async function handleReparse(row) {
  await reparseDocument(row.id)
  ElMessage.success('已触发重新解析')
  fetchDocs()
}

async function handleDelete(row) {
  await deleteDocument(row.id)
  ElMessage.success('已删除')
  fetchDocs()
}

async function viewChunks(row) {
  chunkVisible.value = true
  chunkLoading.value = true
  try {
    const res = await getDocumentChunks(row.id)
    if (res.code === 200) chunks.value = res.data
  } finally {
    chunkLoading.value = false
  }
}
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.page-header h2 { margin: 0; }

.stat-cards { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-bottom: 18px; }
.stat {
  min-width: 86px; padding: 10px 14px; border-radius: 8px;
  background: var(--surface2, #f5f7fa); border: 1px solid var(--border, #ebeef5);
  display: flex; flex-direction: column; align-items: center; gap: 2px;
}
.stat .num { font-size: 20px; font-weight: 700; color: var(--text, #303133); }
.stat .label { font-size: 12px; color: var(--text2, #909399); }
.stat.ok .num { color: #67c23a; }
.stat.warn .num { color: #e6a23c; }
.stat.danger .num { color: #f56c6c; }
.stat-hint { font-size: 12px; color: var(--text2, #909399); display: flex; align-items: center; gap: 6px; }
.stat-hint .dot {
  width: 8px; height: 8px; border-radius: 50%; background: #e6a23c;
  display: inline-block; animation: blink 1s infinite;
}
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }

.filter-bar { margin-bottom: 16px; }
.filter-bar .el-form-item { margin-bottom: 0; }
.pagination-wrap { margin-top: 20px; display: flex; justify-content: center; }
.chunk-item { background: #f9f9f9; border-radius: 6px; padding: 12px; margin-bottom: 12px; }
.chunk-header { font-weight: 600; font-size: 13px; color: #606266; margin-bottom: 6px; }
.chunk-content { font-size: 13px; line-height: 1.6; color: #303133; white-space: pre-wrap; }
</style>
