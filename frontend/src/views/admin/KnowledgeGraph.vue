<template>
  <div class="kg-page">
    <div class="kg-hero">
      <h2>知识图谱可视化</h2>
      <p>探索实体与关系的知识网络</p>
    </div>

    <el-card v-if="rebuildStatus.status !== 'not_started'" class="rebuild-status">
      <div class="rebuild-summary">
        <span class="rebuild-title">图谱全量重建</span>
        <el-tag :type="rebuildTagType">{{ rebuildStatusLabel }}</el-tag>
        <span class="rebuild-progress">
          {{ rebuildStatus.completed_documents || 0 }} / {{ rebuildStatus.total_documents || 0 }} 个文档完成
        </span>
        <span v-if="rebuildStatus.total_chunks">
          {{ rebuildStatus.processed_chunks || 0 }} / {{ rebuildStatus.total_chunks }} 个切块
        </span>
        <span v-if="rebuildStatus.eta_seconds != null">预计剩余 {{ formatEta(rebuildStatus.eta_seconds) }}</span>
        <span v-if="rebuildStatus.failed_documents" class="rebuild-failed">
          {{ rebuildStatus.failed_documents }} 个失败
        </span>
        <el-button
          v-if="rebuildStatus.failed_documents"
          size="small"
          type="warning"
          :loading="retryingRebuild"
          @click="handleRetryFailedRebuild"
        >重试失败文档</el-button>
      </div>
      <el-progress
        :percentage="rebuildPercentage"
        :status="rebuildStatus.status === 'partial_failed' ? 'warning' : undefined"
        :stroke-width="6"
      />
      <details v-if="rebuildStatus.documents?.length" class="rebuild-details">
        <summary>查看文档级进度</summary>
        <div v-for="doc in rebuildStatus.documents" :key="doc.document_id" class="rebuild-document">
          <span class="rebuild-document-title">{{ doc.title || `文档 ${doc.document_id}` }}</span>
          <span>{{ doc.processed_chunks || 0 }} / {{ doc.total_chunks || 0 }} 切块</span>
          <span>{{ doc.percentage || 0 }}%</span>
          <span v-if="doc.failed_batches" class="rebuild-failed">{{ doc.failed_batches }} 个失败分段</span>
        </div>
      </details>
    </el-card>

    <div class="kg-body">
      <div class="graph-wrapper">
        <el-card class="graph-container" v-loading="loading">
          <div class="graph-search-card">
            <el-select v-model="filter.subject_id" placeholder="全部科目" clearable class="graph-subject" @change="fetchGraph">
              <el-option v-for="s in subjects" :key="s.id" :label="s.name" :value="s.id" />
            </el-select>
            <el-input
              v-model="filter.keyword"
              placeholder="搜索实体或关系..."
              clearable
              class="graph-search-input"
              @keyup.enter="handleSearch"
              @clear="handleClearSearch"
            />
            <el-button @click="refreshGraph">刷新</el-button>
          </div>
          <div class="graph-action-card">
            <el-button type="primary" @click="showAddNode">新增实体</el-button>
            <el-button type="success" @click="showAddEdge">新增关系</el-button>
            <el-button type="warning" @click="showGenerateDoc">生成文档</el-button>
            <el-button @click="openCandidateDrawer">候选审核</el-button>
          </div>
          <div ref="graphRef" class="graph-canvas"></div>
          <el-empty v-if="!loading && graphData.nodes.length === 0" description="暂无图谱数据，请先导入种子数据" />
          <div class="graph-hint">滚轮缩放 · 拖动画布 · 双击重置视图 · Neo4j 风格布局</div>
        </el-card>
      </div>
      <el-card class="detail-panel">
        <template #header>
          <span>{{ selectedNode ? '节点详情' : '图例' }}</span>
        </template>
        <div v-if="selectedNode">
          <div class="detail-name">{{ selectedNode.label }}</div>
          <div class="detail-row"><span class="detail-key">ID</span><span class="detail-val">{{ selectedNode.id }}</span></div>
          <div class="detail-row"><span class="detail-key">科目</span><span class="detail-val">{{ subjectName(selectedNode.group) }}</span></div>
          <div v-if="nodeRelations.length" class="detail-rels">
            <div class="detail-rels-title">关联节点</div>
            <div v-for="rel in nodeRelations" :key="rel.id" class="rel-item">
              <span class="rel-dot" :style="{ background: edgeTypeConfig[rel.relation_type]?.color || '#999' }"></span>
              <span class="rel-text">{{ rel.target_name }}</span>
              <span class="rel-type">{{ edgeTypeConfig[rel.relation_type]?.label || rel.relation_type }}</span>
              <el-button size="small" link type="primary" @click.stop="editEdge(rel)">编辑</el-button>
              <el-button size="small" link type="danger" @click.stop="handleDeleteEdge(rel.id)">删除</el-button>
            </div>
          </div>
          <div class="detail-actions">
            <el-button size="small" @click="editNode(selectedNode)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDeleteNode(selectedNode.id)">删除</el-button>
          </div>
        </div>
        <div v-else>
          <div class="graph-legend">
            <div v-for="(cfg, type) in edgeTypeConfig" :key="type" class="legend-item">
              <span class="legend-dot" :style="{ background: cfg.color }"></span>
              <span class="legend-label">{{ cfg.label }}</span>
            </div>
          </div>
          <div class="side-actions">
            <el-button type="primary" size="small" @click="showAddNode">+ 新增实体</el-button>
            <el-button type="success" size="small" @click="showAddEdge">新增关系</el-button>
          </div>
          <div class="stat-item"><span class="stat-num">{{ rebuildStatus.total_nodes ?? graphData.nodes.length }}</span><span class="stat-label">数据库总节点数</span></div>
          <div class="stat-item"><span class="stat-num">{{ graphData.nodes.length }}</span><span class="stat-label">当前显示节点</span></div>
          <div class="stat-item"><span class="stat-num">{{ graphData.edges.length }}</span><span class="stat-label">关系数</span></div>
          <p style="color:#94a3b8;font-size:12px;margin-top:12px">点击节点查看详情 · 双击画布重置视图</p>
        </div>
      </el-card>
    </div>

    <el-dialog v-model="nodeDialog" :title="isEditNode ? '编辑节点' : '添加节点'" width="450px">
      <el-form ref="nodeFormRef" :model="nodeForm" :rules="nodeRules" label-width="70px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="nodeForm.name" />
        </el-form-item>
        <el-form-item label="科目" prop="subject_id">
          <el-select v-model="nodeForm.subject_id" style="width:100%">
            <el-option v-for="s in subjects" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="难度">
          <el-rate v-model="nodeForm.difficulty" :max="5" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="nodeForm.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="nodeDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSaveNode">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="genDocDialog" title="从知识图谱生成文档" width="450px">
      <el-form :model="genDocForm" label-width="80px">
        <el-form-item label="科目">
          <el-select v-model="genDocForm.subject_id" style="width:100%" placeholder="请选择科目">
            <el-option v-for="s in subjects" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="文档类型">
          <el-select v-model="genDocForm.doc_type" style="width:100%">
            <el-option label="学习指南" value="study_guide" />
            <el-option label="考试试卷" value="exam_paper" />
            <el-option label="知识总结" value="summary" />
            <el-option label="教学大纲" value="outline" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="genDocDialog = false">取消</el-button>
        <el-button type="primary" :loading="genDocLoading" @click="handleGenerateDoc">开始生成</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="edgeDialog" :title="isEditEdge ? '编辑关系' : '添加关系'" width="450px">
      <el-form :model="edgeForm" label-width="90px">
        <el-form-item label="源节点">
          <el-select v-model="edgeForm.source_id" filterable style="width:100%">
            <el-option v-for="n in graphData.nodes" :key="n.id" :label="n.label" :value="n.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标节点">
          <el-select v-model="edgeForm.target_id" filterable style="width:100%">
            <el-option v-for="n in graphData.nodes" :key="n.id" :label="n.label" :value="n.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="关系类型">
          <el-select v-model="edgeForm.relation_type" style="width:100%">
            <el-option label="前置条件" value="PREREQUISITE" />
            <el-option label="后继" value="NEXT" />
            <el-option label="关联" value="RELATED" />
            <el-option label="包含" value="CONTAINS" />
            <el-option label="对比" value="CONTRAST" />
            <el-option label="考点" value="EXAMINED_IN" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="edgeForm.description" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="edgeDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSaveEdge">保存</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="candidateDrawer" title="候选关系审核" size="520px">
      <div v-loading="candidateLoading">
        <el-empty v-if="!candidateLoading && !candidates.length" description="暂无待审核候选关系" />
        <el-card v-for="candidate in candidates" :key="candidate.id" class="candidate-card">
          <div class="candidate-title">
            <b>{{ candidate.source_name }}</b>
            <span>→</span>
            <b>{{ candidate.target_name }}</b>
          </div>
          <div class="candidate-meta">
            <el-tag size="small">{{ edgeTypeConfig[candidate.relation_type]?.label || candidate.relation_type }}</el-tag>
            <span>置信度 {{ (candidate.confidence * 100).toFixed(0) }}%</span>
          </div>
          <p>{{ candidate.description || '暂无关系说明' }}</p>
          <div class="candidate-evidence">证据：{{ candidate.evidence_text || '暂无证据文本' }}</div>
          <div class="candidate-source">来源：{{ candidate.document_title || '未知文档' }}</div>
          <div class="candidate-actions">
            <el-button size="small" type="primary" @click="reviewCandidate(candidate.id, true)">批准入图</el-button>
            <el-button size="small" type="danger" plain @click="reviewCandidate(candidate.id, false)">驳回</el-button>
          </div>
        </el-card>
        <el-pagination
          v-if="candidateTotal > candidateSize"
          layout="prev, pager, next"
          :total="candidateTotal"
          :page-size="candidateSize"
          v-model:current-page="candidatePage"
          @current-change="fetchCandidates"
        />
      </div>
    </el-drawer>
  </div>
</template>
<script setup>
import { ref, computed, onMounted, onBeforeUnmount, onActivated, onDeactivated, nextTick } from 'vue'
import { ElMessage, ElNotification } from 'element-plus'
import { Network } from 'vis-network'
import 'vis-network/styles/vis-network.css'
import { getSubgraph, searchSubgraph, createPoint, updatePoint, deletePoint, createRelation, updateRelation, deleteRelation, generateDocument, getRebuildStatus, retryFailedRebuildDocuments, getRelationCandidates, approveRelationCandidate, rejectRelationCandidate } from '@/api/kg'
import { getSubjects } from '@/api/subjects'
import { useAutoRefresh } from '@/composables/useAutoRefresh'

// ── State ──
const graphRef = ref(null)
const loading = ref(false)
const subjects = ref([])
const filter = ref({ subject_id: null, keyword: '' })
const graphData = ref({ nodes: [], edges: [] })
const selectedNode = ref(null)
const nodeRelations = ref([])
const rebuildStatus = ref({ status: 'not_started', total_documents: 0, completed_documents: 0, failed_documents: 0 })
const retryingRebuild = ref(false)
const candidateDrawer = ref(false)
const candidateLoading = ref(false)
const candidates = ref([])
const candidatePage = ref(1)
const candidateSize = 20
const candidateTotal = ref(0)
const GRAPH_PAGE_SIZE = 300
let network = null

// ── Edge type config ──
const edgeTypeConfig = {
  PREREQUISITE: { color: '#f472b6', dashes: 'dashed', label: '前置条件' },
  NEXT:         { color: '#38bdf8', dashes: 'solid',  label: '后继' },
  RELATED:      { color: '#a78bfa', dashes: 'solid',  label: '关联' },
  CONTAINS:     { color: '#4ade80', dashes: 'dotted', label: '包含' },
  CONTRAST:     { color: '#fbbf24', dashes: 'dashed', label: '对比' },
  EXAMINED_IN:  { color: '#fb923c', dashes: 'dotted', label: '考点' },
}

// ── Node CRUD state ──
const nodeDialog = ref(false)
const isEditNode = ref(false)
const saving = ref(false)
const nodeFormRef = ref(null)
const nodeForm = ref({ name: '', subject_id: null, difficulty: 3, description: '' })
const nodeRules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
  subject_id: [{ required: true, message: '请选择科目', trigger: 'change' }],
}

// ── Edge CRUD state ──
const edgeDialog = ref(false)
const isEditEdge = ref(false)
const edgeForm = ref({ source_id: null, target_id: null, relation_type: 'RELATED', description: '' })

// ── Gen doc state ──
const genDocDialog = ref(false)
const genDocLoading = ref(false)
const genDocForm = ref({ subject_id: null, doc_type: 'study_guide' })

// ── Neo4j Browser-like palette for node groups on dark canvas ──
const GROUP_COLORS = [
  { bg: '#22d3ee', border: '#67e8f9', highlight: '#a5f3fc', text: '#e0f2fe' },
  { bg: '#60a5fa', border: '#93c5fd', highlight: '#bfdbfe', text: '#dbeafe' },
  { bg: '#34d399', border: '#86efac', highlight: '#bbf7d0', text: '#dcfce7' },
  { bg: '#fbbf24', border: '#fde68a', highlight: '#fef3c7', text: '#fef9c3' },
  { bg: '#a78bfa', border: '#c4b5fd', highlight: '#ddd6fe', text: '#ede9fe' },
  { bg: '#fb7185', border: '#fda4af', highlight: '#fecdd3', text: '#ffe4e6' },
  { bg: '#f472b6', border: '#f9a8d4', highlight: '#fbcfe8', text: '#fce7f3' },
  { bg: '#94a3b8', border: '#cbd5e1', highlight: '#e2e8f0', text: '#f1f5f9' },
]

function getGroupColor(group) {
  return GROUP_COLORS[parseInt(group) % GROUP_COLORS.length] || GROUP_COLORS[0]
}

function getEdgeStyle(type) {
  const cfg = edgeTypeConfig[type] || { color: '#94a3b8', dashes: 'solid' }
  return {
    color: cfg.color,
    dashes: cfg.dashes === 'dashed' ? [10, 6] : cfg.dashes === 'dotted' ? [3, 6] : false,
    opacity: 0.42,
  }
}

// ── Degree computation ──
function computeDegree(data = graphData.value) {
  const deg = {}
  for (const e of data.edges) {
    deg[e.from] = (deg[e.from] || 0) + 1
    deg[e.to] = (deg[e.to] || 0) + 1
  }
  return deg
}

const renderEdgeCount = computed(() => graphData.value.edges.length)

// ── Lifecycle ──
const { refresh: autoRefresh, stopPolling: stopAutoRefresh, startPolling: startAutoRefresh } = useAutoRefresh(() => {
  fetchRebuildStatus()
}, 30000)

onMounted(() => {
  fetchSubjects()
  fetchGraph()
  fetchRebuildStatus()
  window.addEventListener('resize', handleResize)
})

onActivated(() => {
  if (graphData.value.nodes.length > 0) autoRefresh()
})

onDeactivated(() => { stopAutoRefresh() })

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (network) network.destroy()
})

function handleResize() {
  if (network && graphRef.value) network.fit({ animation: false })
}

// ── Rebuild status ──
const rebuildPercentage = computed(() => {
  if (rebuildStatus.value.total_chunks) return rebuildStatus.value.percentage || 0
  const total = rebuildStatus.value.total_documents || 0
  return total ? Math.round(((rebuildStatus.value.completed_documents || 0) / total) * 100) : 0
})

function formatEta(seconds) {
  if (seconds < 60) return `${seconds} 秒`
  if (seconds < 3600) return `${Math.ceil(seconds / 60)} 分钟`
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.ceil((seconds % 3600) / 60)
  return `${hours} 小时 ${minutes} 分钟`
}

const rebuildStatusLabel = computed(() => ({
  queued: '排队中', running: '重建中', success: '已完成', partial_failed: '部分失败', failed: '失败',
}[rebuildStatus.value.status] || '未开始'))

const rebuildTagType = computed(() => ({
  queued: 'info', running: 'primary', success: 'success', partial_failed: 'warning', failed: 'danger',
}[rebuildStatus.value.status] || 'info'))

async function fetchRebuildStatus() {
  try {
    const res = await getRebuildStatus()
    if (res.code === 200) rebuildStatus.value = res.data
  } catch {}
}

async function handleRetryFailedRebuild() {
  retryingRebuild.value = true
  try {
    const res = await retryFailedRebuildDocuments()
    if (res.code === 200) {
      ElMessage.success(`已重新排队 ${res.data.queued_documents} 个文档`)
      await fetchRebuildStatus()
    }
  } finally { retryingRebuild.value = false }
}

// ── Candidate review ──
async function openCandidateDrawer() {
  candidateDrawer.value = true
  candidatePage.value = 1
  await fetchCandidates()
}

async function fetchCandidates() {
  candidateLoading.value = true
  try {
    const res = await getRelationCandidates({ status: 'pending', page: candidatePage.value, size: candidateSize })
    if (res.code === 200) {
      candidates.value = res.data.items || []
      candidateTotal.value = res.data.total || 0
    }
  } finally { candidateLoading.value = false }
}

async function reviewCandidate(id, approved) {
  if (approved) await approveRelationCandidate(id)
  else await rejectRelationCandidate(id)
  ElMessage.success(approved ? '候选关系已批准' : '候选关系已驳回')
  await fetchCandidates()
  if (approved) refreshGraph()
}

// ── Data fetching (simplified: no cache, no pagination) ──
async function fetchSubjects() {
  try {
    const res = await getSubjects()
    if (res.code === 200) {
      subjects.value = res.data.map(s => ({ id: s.id, name: s.name }))
    }
  } catch {}
}

async function fetchGraph(silent = false) {
  if (!silent) loading.value = true
  try {
    const params = {}
    if (filter.value.subject_id) params.subject_id = filter.value.subject_id

    const keyword = filter.value.keyword.trim()
    if (keyword) {
      const res = await searchSubgraph({ keyword, ...params })
      if (res.code === 200) {
        if (res.data.error) throw new Error(res.data.error)
        if (res.data.warning) ElMessage.warning(res.data.warning)
        graphData.value = { nodes: res.data.nodes || [], edges: res.data.edges || [] }
      }
    } else {
      const res = await getSubgraph({ ...params, offset: 0, size: GRAPH_PAGE_SIZE })
      if (res.code === 200) {
        if (res.data.error) throw new Error(res.data.error)
        graphData.value = { nodes: res.data.nodes || [], edges: res.data.edges || [] }
      }
    }
    syncSelectedNode()
    await nextTick()
    await new Promise(r => requestAnimationFrame(r))
    renderGraph()
  } catch (error) {
    if (!silent) ElMessage.error('获取图谱失败：' + (error.message || '网络异常'))
  } finally {
    if (!silent) loading.value = false
  }
}

async function refreshGraph() {
  await fetchGraph()
}

async function handleSearch() {
  filter.value.keyword = filter.value.keyword.trim()
  if (!filter.value.keyword) { await handleClearSearch(); return }
  await fetchGraph()
}

function handleClearSearch() {
  filter.value.keyword = ''
  fetchGraph()
}

// ═══════════════════════════════════════════════════════════════
//  Neo4j-style graph rendering: barnesHut physics with repulsion
//  between ALL nodes. Labels always visible. No degree limiter.
// ═══════════════════════════════════════════════════════════════

function renderGraph() {
  if (!graphRef.value) return
  const data = graphData.value
  if (!data.nodes.length) {
    if (network) { network.destroy(); network = null }
    return
  }

  // Clean previous instance
  if (network) { network.destroy(); network = null }

  const degree = computeDegree(data)
  const maxDeg = Math.max(1, ...Object.values(degree))

  // ── Nodes: Neo4j Browser style circles with degree-based size ──
  const nodes = data.nodes.map(n => {
    const colors = getGroupColor(n.group || '0')
    const nodeDeg = degree[n.id] || 0
    const size = 14 + Math.round((nodeDeg / maxDeg) * 26)

    return {
      id: n.id,
      label: n.label,
      group: n.group || '0',
      title: `<div style="padding:8px 12px;font-size:13px;line-height:1.6"><b>${n.label}</b><br/><span style="color:#94a3b8;font-size:12px">关联 ${nodeDeg} 个节点</span></div>`,
      size,
      font: {
        size: 11,
        color: colors.text,
        face: "'PingFang SC','Microsoft YaHei','Helvetica Neue',Arial,sans-serif",
        strokeWidth: 3,
        strokeColor: '#0f172a',
      },
      borderWidth: 2,
      borderWidthSelected: 4,
      color: {
        background: colors.bg,
        border: colors.border,
        highlight: { background: colors.highlight, border: colors.border },
        hover: { background: colors.highlight, border: colors.border },
      },
      shape: 'dot',
      mass: 1 + nodeDeg * 0.05,
    }
  })

  // ── Edges: clean subtle lines with arrows ──
  const edges = data.edges.map(e => {
    const style = getEdgeStyle(e.label)
    return {
      id: e.id,
      from: e.from,
      to: e.to,
      label: edgeTypeConfig[e.label]?.label || e.label,
      title: e.title || e.label,
      arrows: { to: { enabled: true, scaleFactor: 0.5, type: 'arrow' } },
      font: {
        size: 9,
        color: style.color,
        face: "'PingFang SC','Microsoft YaHei',Arial,sans-serif",
        align: 'middle',
        strokeWidth: 3,
        strokeColor: '#0f172a',
        background: 'rgba(15,23,42,0.55)',
      },
      smooth: { type: 'dynamic', roundness: 0.08 },
      color: { color: style.color, highlight: style.color, hover: style.color, opacity: style.opacity },
      width: 0.8,
      dashes: style.dashes,
      selectionWidth: 1.8,
      hoverWidth: 1.8,
    }
  })

  // ── Neo4j-style barnesHut physics: repulsion between ALL nodes ──
  const options = {
    autoResize: false,
    backgroundColor: '#0f172a',
    physics: {
      enabled: true,
      stabilization: { iterations: 260, updateInterval: 20 },
      solver: 'barnesHut',
      barnesHut: {
        gravitationalConstant: -5200,
        centralGravity: 0.12,
        springLength: 260,
        springConstant: 0.025,
        damping: 0.42,
        avoidOverlap: 1.2,
      },
      maxVelocity: 35,
      minVelocity: 0.15,
      timestep: 0.4,
    },
    interaction: {
      hover: true,
      tooltipDelay: 150,
      selectConnectedEdges: true,
      multiselect: false,
      navigationButtons: false,
      keyboard: true,
      zoomView: true,
      dragView: true,
    },
    edges: {
      color: 'rgba(148,163,184,0.30)',
      width: 0.8,
      smooth: { type: 'dynamic', roundness: 0.08 },
    },
    nodes: {
      shape: 'dot',
      size: 18,
      font: {
        size: 11,
        color: '#e2e8f0',
        face: "'PingFang SC','Microsoft YaHei','Helvetica Neue',Arial,sans-serif",
        strokeWidth: 3,
        strokeColor: '#0f172a',
      },
      borderWidth: 2,
      borderWidthSelected: 4,
    },
  }

  const container = graphRef.value
  network = new Network(container, { nodes, edges }, options)

  // ── Events ──

  // After stabilization: fit view & keep physics alive
  network.once('stabilizationIterationsDone', () => {
    network.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } })
    // Keep physics on so nodes can be repositioned by drag
  })

  // Click: select node or edge
  network.on('click', (params) => {
    if (params.nodes.length) {
      const nodeId = params.nodes[0]
      const node = data.nodes.find(n => n.id === nodeId)
      selectedNode.value = node || null
      nodeRelations.value = node ? relationsForNode(nodeId) : []
    } else if (params.edges.length) {
      const edgeId = params.edges[0]
      const edge = data.edges.find(e => String(e.id) === String(edgeId))
      if (edge) editEdge(edge)
    } else {
      selectedNode.value = null
      nodeRelations.value = []
    }
  })

  // Double click: reset view
  network.on('doubleClick', () => {
    network.fit({ animation: { duration: 500, easingFunction: 'easeInOutQuad' } })
  })

  // Drag: re-enable physics so nodes redistribute naturally
  network.on('dragStart', () => {
    network.setOptions({
      physics: {
        enabled: true,
        stabilization: { enabled: false },
        solver: 'barnesHut',
        barnesHut: {
          gravitationalConstant: -5200,
          centralGravity: 0.12,
          springLength: 260,
          springConstant: 0.025,
          damping: 0.42,
          avoidOverlap: 1.2,
        },
      },
    })
  })

  // After drag: let it settle then keep physics alive
  network.on('dragEnd', () => {
    // Keep physics enabled — nodes will naturally find equilibrium
    // with real-time repulsion/attraction forces
  })
}

// ── Relations for selected node ──
function relationsForNode(nodeId) {
  const relations = []
  for (const edge of graphData.value.edges) {
    if (String(edge.from) === String(nodeId)) {
      const target = graphData.value.nodes.find(node => String(node.id) === String(edge.to))
      if (target) relations.push({
        id: edge.id, source_id: edge.from, target_id: edge.to,
        target_name: target.label, relation_type: edge.label,
        description: edge.description || edge.title || '',
      })
    }
    if (String(edge.to) === String(nodeId)) {
      const source = graphData.value.nodes.find(node => String(node.id) === String(edge.from))
      if (source) relations.push({
        id: edge.id, source_id: edge.from, target_id: edge.to,
        target_name: source.label, relation_type: edge.label,
        description: edge.description || edge.title || '',
      })
    }
  }
  return relations
}

function syncSelectedNode() {
  const selectedId = selectedNode.value?.id
  if (!selectedId) return
  const node = graphData.value.nodes.find(item => String(item.id) === String(selectedId))
  if (!node) { selectedNode.value = null; nodeRelations.value = [] }
  else { selectedNode.value = node; nodeRelations.value = relationsForNode(selectedId) }
}

function subjectName(group) {
  return subjects.value.find(subject => String(subject.id) === String(group))?.name || group || '未知'
}

// ═══════════════════════════════════════════════════════════════
//  Node CRUD
// ═══════════════════════════════════════════════════════════════

function showAddNode() {
  isEditNode.value = false
  nodeForm.value = { name: '', subject_id: filter.value.subject_id || null, difficulty: 3, description: '' }
  nodeDialog.value = true
}

function editNode(node) {
  isEditNode.value = true
  nodeForm.value = {
    name: node.label, subject_id: parseInt(node.group) || null, difficulty: 3, description: '',
    _id: node.id,
  }
  nodeDialog.value = true
}

async function handleSaveNode() {
  const valid = await nodeFormRef.value.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    if (isEditNode.value) {
      await updatePoint(nodeForm.value._id, nodeForm.value)
      ElMessage.success('更新成功')
    } else {
      await createPoint(nodeForm.value)
      ElMessage.success('创建成功')
    }
    nodeDialog.value = false
    refreshGraph()
  } finally { saving.value = false }
}

async function handleDeleteNode(id) {
  try {
    await deletePoint(id)
    ElMessage.success('已删除')
    selectedNode.value = null
    nodeRelations.value = []
    refreshGraph()
  } catch {}
}

// ═══════════════════════════════════════════════════════════════
//  Edge CRUD
// ═══════════════════════════════════════════════════════════════

function showAddEdge() {
  isEditEdge.value = false
  edgeForm.value = { source_id: null, target_id: null, relation_type: 'RELATED', description: '' }
  edgeDialog.value = true
}

function editEdge(edge) {
  if (!edge?.id) {
    ElMessage.warning('该关系缺少 ID，请刷新图谱后再编辑')
    return
  }
  isEditEdge.value = true
  edgeForm.value = {
    _id: edge.id,
    source_id: edge.source_id || edge.from,
    target_id: edge.target_id || edge.to,
    relation_type: edge.relation_type || edge.label || 'RELATED',
    description: edge.description || edge.title || '',
  }
  edgeDialog.value = true
}

async function handleSaveEdge() {
  if (!edgeForm.value.source_id || !edgeForm.value.target_id) {
    ElMessage.warning('请选择源节点和目标节点')
    return
  }
  if (String(edgeForm.value.source_id) === String(edgeForm.value.target_id)) {
    ElMessage.warning('源节点和目标节点不能相同')
    return
  }
  saving.value = true
  try {
    const payload = {
      source_id: edgeForm.value.source_id,
      target_id: edgeForm.value.target_id,
      relation_type: edgeForm.value.relation_type,
      description: edgeForm.value.description,
    }
    if (isEditEdge.value) {
      await updateRelation(edgeForm.value._id, payload)
      ElMessage.success('关系已更新')
    } else {
      await createRelation(payload)
      ElMessage.success('关系已创建')
    }
    edgeDialog.value = false
    refreshGraph()
  } finally { saving.value = false }
}

async function handleDeleteEdge(id) {
  if (!id) return
  saving.value = true
  try {
    await deleteRelation(id)
    ElMessage.success('关系已删除')
    await refreshGraph()
  } finally { saving.value = false }
}

// ═══════════════════════════════════════════════════════════════
//  Document generation
// ═══════════════════════════════════════════════════════════════

function showGenerateDoc() {
  genDocForm.value = { subject_id: filter.value.subject_id, doc_type: 'study_guide' }
  genDocDialog.value = true
}

async function handleGenerateDoc() {
  if (!genDocForm.value.subject_id) {
    ElMessage.warning('请选择科目')
    return
  }
  genDocLoading.value = true
  try {
    const res = await generateDocument(genDocForm.value)
    if (res.code === 200) {
      ElMessage.success('文档生成成功，正在解析中...')
      genDocDialog.value = false
    } else {
      ElMessage.error(res.message || '生成失败')
    }
  } catch {
    ElMessage.error('生成失败，请重试')
  } finally { genDocLoading.value = false }
}
</script>
<style scoped>
.kg-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: 22px;
  overflow: hidden;
  color: var(--text);
}

.kg-hero {
  flex-shrink: 0;
  padding: 6px 0 0;
}
.kg-hero h2 {
  margin: 0;
  font-size: 24px;
  font-weight: 800;
  letter-spacing: 0.2px;
  color: var(--text);
}
.kg-hero p {
  margin: 10px 0 0;
  font-size: 15px;
  color: var(--text2);
}

.rebuild-status {
  flex-shrink: 0;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: rgba(26, 26, 46, 0.82);
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.22);
}
.rebuild-status :deep(.el-card__body) { padding: 10px 16px; }
.rebuild-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
  font-size: 12px;
  color: #64748b;
}
.rebuild-title { font-weight: 700; color: var(--text); }
.rebuild-progress { margin-left: auto; }
.rebuild-failed { color: #d97706; }
.rebuild-details { margin-top: 8px; font-size: 12px; color: #64748b; }
.rebuild-details summary { cursor: pointer; }
.rebuild-document { display: flex; gap: 12px; padding: 5px 0 0; }
.rebuild-document-title { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.candidate-card { margin-bottom: 12px; }
.candidate-title { display:flex; gap:8px; align-items:center; color:#334155; }
.candidate-meta { display:flex; gap:10px; align-items:center; margin-top:8px; font-size:12px; color:#64748b; }
.candidate-card p { margin:10px 0 6px; font-size:13px; color:#475569; }
.candidate-evidence { padding:8px; border-radius:6px; background:#f8fafc; font-size:12px; line-height:1.6; color:#64748b; }
.candidate-source { margin-top:6px; font-size:12px; color:#94a3b8; }
.candidate-actions { display:flex; gap:8px; margin-top:10px; }

/* ── Layout ── */
.kg-body {
  flex: 1;
  display: flex;
  gap: 20px;
  min-height: 0;
  overflow: hidden;
}

.graph-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

/* ── Neo4j-style graph container on the system dark theme ── */
.graph-container {
  flex: 1;
  position: relative;
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 14px;
  box-shadow: 0 22px 52px rgba(0, 0, 0, 0.28);
  overflow: hidden;
  min-height: 0;
  background: rgba(15, 15, 26, 0.92);
}
.graph-container :deep(.el-card__body) {
  flex: 1;
  padding: 0;
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(circle at 50% 42%, rgba(14, 165, 233, 0.12), transparent 34%),
    linear-gradient(135deg, rgba(15, 23, 42, 0.96), rgba(17, 24, 39, 0.92));
}

.graph-canvas {
  width: 100%;
  height: 100%;
}

.graph-hint {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 11px;
  color: #cbd5e1;
  pointer-events: none;
  z-index: 1;
  background: rgba(15, 23, 42, 0.76);
  backdrop-filter: blur(4px);
  padding: 4px 16px;
  border-radius: 20px;
  white-space: nowrap;
  border: 1px solid rgba(148, 163, 184, 0.26);
}

/* ── Floating control cards ── */
.graph-search-card,
.graph-action-card {
  position: absolute;
  z-index: 3;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.82);
  border: 1px solid rgba(148, 163, 184, 0.24);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.24);
  backdrop-filter: blur(10px);
}
.graph-search-card { top: 22px; left: 22px; }
.graph-action-card { top: 22px; right: 22px; }
.graph-subject { width: 118px; }
.graph-search-input { width: 220px; }
.graph-search-card :deep(.el-input__wrapper),
.graph-search-card :deep(.el-select__wrapper) {
  background: rgba(15, 23, 42, 0.7);
  box-shadow: 0 0 0 1px rgba(148, 163, 184, 0.24) inset;
  color: #e2e8f0;
}

/* ── Legend ── */
.graph-legend {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 6px 0 18px;
  background: transparent;
  border-bottom: 1px solid rgba(148, 163, 184, 0.22);
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 12px;
}
.legend-dot {
  width: 13px;
  height: 13px;
  border-radius: 50%;
  flex-shrink: 0;
}
.legend-label { font-size: 15px; color: var(--text2); }

/* ── Detail Panel ── */
.detail-panel {
  width: 300px;
  flex-shrink: 0;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 14px;
  box-shadow: 0 22px 52px rgba(0, 0, 0, 0.28);
  background: rgba(26, 26, 46, 0.84);
  overflow: hidden;
}
.detail-panel :deep(.el-card__header) {
  background: rgba(15, 23, 42, 0.66);
  border-bottom: 1px solid rgba(148, 163, 184, 0.22);
  font-weight: 700;
  color: #e2e8f0;
  font-size: 18px;
  padding: 18px 26px;
}
.detail-panel :deep(.el-card__body) { padding: 26px; }
.side-actions {
  display: flex;
  gap: 10px;
  padding: 18px 0;
  border-bottom: 1px solid rgba(148, 163, 184, 0.22);
}
.side-actions .el-button { flex: 1; font-weight: 700; }
.detail-name {
  font-size: 17px;
  font-weight: 700;
  color: #e2e8f0;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.22);
}
.detail-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
}
.detail-key { color: #94a3b8; flex-shrink: 0; width: 32px; font-weight: 500; }
.detail-val { color: #e2e8f0; }
.detail-rels {
  margin-top: 14px;
  border-top: 1px solid rgba(148, 163, 184, 0.22);
  padding-top: 12px;
}
.detail-rels-title {
  font-size: 12px;
  font-weight: 600;
  color: #94a3b8;
  margin-bottom: 8px;
}
.detail-actions {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid rgba(148, 163, 184, 0.22);
  display: flex;
  gap: 8px;
}

.stat-item {
  text-align: left;
  padding: 0;
  margin-top: 12px;
}
.stat-item + .stat-item { border-top: none; }
.stat-num {
  display: inline;
  font-size: 16px;
  font-weight: 800;
  color: #e2e8f0;
  line-height: 1.2;
}
.stat-label {
  display: inline;
  font-size: 16px;
  color: #94a3b8;
  margin-left: 0;
}

.rel-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  font-size: 12px;
  border-radius: 6px;
  margin-bottom: 4px;
  background: rgba(15, 23, 42, 0.48);
  transition: background 0.15s;
}
.rel-item:hover { background: rgba(124, 58, 237, 0.18); }
.rel-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.rel-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #e2e8f0;
  font-weight: 500;
}
.rel-type {
  font-size: 10px;
  color: #cbd5e1;
  background: rgba(148, 163, 184, 0.16);
  padding: 1px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}

.kg-page :deep(.el-card) { border-radius: 10px; }
.kg-page :deep(.vis-network:focus) { outline: none; }
.kg-page :deep(.vis-network),
.kg-page :deep(.vis-network canvas) {
  background: transparent !important;
}
.kg-page :deep(.vis-tooltip) {
  background: rgba(30, 41, 59, 0.95) !important;
  color: #e2e8f0 !important;
  border: 1px solid rgba(148, 163, 184, 0.2) !important;
  border-radius: 8px !important;
  box-shadow: 0 8px 24px rgba(0,0,0,0.15) !important;
  padding: 6px 10px !important;
  font-family: 'PingFang SC','Microsoft YaHei',sans-serif !important;
}
</style>
