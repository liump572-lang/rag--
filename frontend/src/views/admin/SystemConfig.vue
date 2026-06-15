<template>
  <div class="config-page">
    <div class="page-toolbar">
      <h2>系统设置</h2>
      <span class="toolbar-hint">配置保存后在下一次调用（问答 / 解析 / 图谱抽取 / 向量化）即生效</span>
    </div>

    <!-- ──────────── LLM 配置 ──────────── -->
    <el-card class="section-card">
      <template #header><span class="card-title">LLM 大模型</span></template>
      <el-form :model="llmForm" label-width="120px">
        <el-form-item label="API Base URL">
          <el-input v-model="llmForm.api_base" placeholder="https://api.deepseek.com/v1" />
        </el-form-item>
        <el-form-item label="模型">
          <div class="model-row">
            <el-select
              v-model="llmForm.model" filterable allow-create default-first-option
              placeholder="选择或输入模型名" style="flex:1"
            >
              <el-option v-for="m in llmModels" :key="m" :label="m" :value="m" />
            </el-select>
            <el-button :loading="llmFetching" @click="fetchInto('llm')">拉取模型</el-button>
          </div>
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="llmForm.api_key" type="password" show-password
            :placeholder="`当前：${settings.llm.api_key_masked}（留空表示不修改）`" />
        </el-form-item>
        <el-form-item label="采样参数">
          <div class="param-row">
            <span>temperature</span>
            <el-input-number v-model="llmForm.temperature" :min="0" :max="2" :step="0.1" :precision="2" size="small" />
            <span>top_p</span>
            <el-input-number v-model="llmForm.top_p" :min="0" :max="1" :step="0.05" :precision="2" size="small" />
            <span>max_tokens</span>
            <el-input-number v-model="llmForm.max_tokens" :min="1" :max="32768" :step="256" size="small" />
          </div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="savingLlm" @click="saveLlm">保存 LLM 设置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ──────────── Embedding 配置 ──────────── -->
    <el-card class="section-card">
      <template #header><span class="card-title">Embedding 向量模型</span></template>
      <el-form :model="embForm" label-width="120px">
        <el-form-item label="API Base URL">
          <el-input v-model="embForm.api_base" placeholder="https://api.deepseek.com/v1" />
        </el-form-item>
        <el-form-item label="模型">
          <div class="model-row">
            <el-select
              v-model="embForm.model" filterable allow-create default-first-option
              placeholder="选择或输入模型名" style="flex:1"
            >
              <el-option v-for="m in embModels" :key="m" :label="m" :value="m" />
            </el-select>
            <el-button :loading="embFetching" @click="fetchInto('embedding')">拉取模型</el-button>
          </div>
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="embForm.api_key" type="password" show-password
            :placeholder="`当前：${settings.embedding.api_key_masked}（留空表示不修改）`" />
        </el-form-item>
        <el-form-item label="向量维度">
          <el-input-number v-model="embForm.dimension" :min="64" :max="8192" :step="128" />
          <span class="field-hint" style="margin-left:10px">改变维度将使用新的向量集合，存量文档需重新解析</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="savingEmb" @click="saveEmbedding">保存 Embedding 设置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ──────────── 检索配置 ──────────── -->
    <el-card class="section-card">
      <template #header><span class="card-title">检索参数</span></template>
      <el-form :model="retrievalForm" label-width="120px">
        <el-form-item label="Top-K">
          <el-input-number v-model="retrievalForm.top_k" :min="1" :max="50" />
        </el-form-item>
        <el-form-item label="相似度阈值">
          <el-input-number v-model="retrievalForm.similarity_threshold" :min="0" :max="1" :step="0.05" :precision="2" />
        </el-form-item>
        <el-form-item label="向量/图谱权重">
          <div class="param-row">
            <span>vector</span>
            <el-input-number v-model="retrievalForm.vector_weight" :min="0" :max="1" :step="0.1" :precision="2" size="small" />
            <span>graph</span>
            <el-input-number v-model="retrievalForm.graph_weight" :min="0" :max="1" :step="0.1" :precision="2" size="small" />
          </div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="savingRetrieval" @click="saveRetrieval">保存检索设置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ──────────── 模型档案 ──────────── -->
    <el-card class="section-card">
      <template #header>
        <div class="card-head-flex">
          <span class="card-title">模型档案</span>
          <div>
            <el-button size="small" @click="openProfile('llm')">+ LLM 档案</el-button>
            <el-button size="small" @click="openProfile('embedding')">+ Embedding 档案</el-button>
          </div>
        </div>
      </template>
      <el-table :data="profiles" empty-text="暂无已保存档案，可保存多套配置随时切换" stripe>
        <el-table-column label="类型" width="110">
          <template #default="{ row }">
            <el-tag size="small" :type="row.type === 'llm' ? 'primary' : 'success'">
              {{ row.type === 'llm' ? 'LLM' : 'Embedding' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="name" label="名称" min-width="120" />
        <el-table-column prop="model" label="模型" min-width="160" show-overflow-tooltip />
        <el-table-column prop="api_url" label="API 地址" min-width="200" show-overflow-tooltip />
        <el-table-column label="Key" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.api_key_configured ? 'success' : 'info'">
              {{ row.api_key_configured ? '已配置' : '未配置' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.active" size="small" type="warning">当前使用</el-tag>
            <span v-else style="color:var(--text3);font-size:12px">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="210" fixed="right">
          <template #default="{ row }">
            <el-button size="small" :disabled="row.active" @click="activate(row)">设为当前</el-button>
            <el-button size="small" @click="openProfile(row.type, row)">编辑</el-button>
            <el-button size="small" type="danger" @click="removeProfile(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ──────────── 高级配置 ──────────── -->
    <el-card class="section-card">
      <template #header>
        <div class="card-head-flex">
          <span class="card-title">高级配置（原始键值）</span>
          <el-button size="small" @click="showAdd = true">新增配置</el-button>
        </div>
      </template>
      <el-table :data="configs" v-loading="loadingConfigs" empty-text="暂无配置项" stripe>
        <el-table-column prop="config_key" label="配置键" min-width="180">
          <template #default="{ row }"><code style="font-size:12px">{{ row.config_key }}</code></template>
        </el-table-column>
        <el-table-column prop="config_value" label="配置值" min-width="240" show-overflow-tooltip />
        <el-table-column prop="description" label="说明" min-width="140">
          <template #default="{ row }">{{ row.description || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="editConfig(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="removeConfig(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 档案对话框 -->
    <el-dialog v-model="profileVisible" :title="profileDialogTitle" width="560px">
      <el-form :model="profileForm" label-width="110px">
        <el-form-item label="名称">
          <el-input v-model="profileForm.name" placeholder="如：DeepSeek 生产 / 硅基流动 bge-m3" />
        </el-form-item>
        <el-form-item label="API Base URL">
          <el-input v-model="profileForm.api_url" placeholder="https://.../v1" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="profileForm.api_key" type="password" show-password
            :placeholder="editingProfile ? '留空表示不修改' : '请输入 API Key'" />
        </el-form-item>
        <el-form-item label="模型">
          <div class="model-row">
            <el-select v-model="profileForm.model" filterable allow-create default-first-option
              placeholder="选择或输入模型名" style="flex:1">
              <el-option v-for="m in profileModels" :key="m" :label="m" :value="m" />
            </el-select>
            <el-button :loading="profileFetching" @click="fetchInto('profile')">拉取模型</el-button>
          </div>
        </el-form-item>
        <el-form-item v-if="profileForm.type === 'embedding'" label="向量维度">
          <el-input-number v-model="profileForm.dimension" :min="64" :max="8192" :step="128" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="profileVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingProfile" @click="saveProfile">保存</el-button>
      </template>
    </el-dialog>

    <!-- 新增配置对话框 -->
    <el-dialog v-model="showAdd" title="新增配置" width="500px">
      <el-form :model="addForm" label-width="80px">
        <el-form-item label="配置键"><el-input v-model="addForm.config_key" /></el-form-item>
        <el-form-item label="配置值"><el-input v-model="addForm.config_value" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="说明"><el-input v-model="addForm.description" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showAdd = false">取消</el-button>
        <el-button type="primary" :loading="savingConfig" @click="addConfig">保存</el-button>
      </template>
    </el-dialog>

    <!-- 编辑配置对话框 -->
    <el-dialog v-model="showEdit" title="编辑配置" width="500px">
      <el-form :model="editForm" label-width="80px">
        <el-form-item label="配置键"><el-input :model-value="editForm.config_key" disabled /></el-form-item>
        <el-form-item label="配置值"><el-input v-model="editForm.config_value" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="说明"><el-input v-model="editForm.description" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEdit = false">取消</el-button>
        <el-button type="primary" :loading="savingConfig" @click="saveEditConfig">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getSettings, saveSettings, getProfiles, createProfile, updateProfile,
  deleteProfile, activateProfile, fetchModels,
  getConfigs, createConfig, updateConfig, deleteConfig,
} from '@/api/systemConfig'

// ── 当前生效配置 ──
const settings = reactive({
  llm: { model: '', api_base: '', api_key_masked: '未配置', temperature: 0.7, top_p: 0.9, max_tokens: 4096 },
  embedding: { model: '', api_base: '', api_key_masked: '未配置', dimension: 1024 },
  retrieval: { top_k: 10, similarity_threshold: 0.75, vector_weight: 0.6, graph_weight: 0.4 },
})
const llmForm = reactive({ api_base: '', model: '', api_key: '', temperature: 0.7, top_p: 0.9, max_tokens: 4096 })
const embForm = reactive({ api_base: '', model: '', api_key: '', dimension: 1024 })
const retrievalForm = reactive({ top_k: 10, similarity_threshold: 0.75, vector_weight: 0.6, graph_weight: 0.4 })
const savingLlm = ref(false)
const savingEmb = ref(false)
const savingRetrieval = ref(false)

// ── 模型拉取 ──
const llmModels = ref([])
const embModels = ref([])
const profileModels = ref([])
const llmFetching = ref(false)
const embFetching = ref(false)
const profileFetching = ref(false)

// ── 档案 ──
const profiles = ref([])
const profileVisible = ref(false)
const editingProfile = ref(null)
const savingProfile = ref(false)
const profileForm = reactive({ type: 'llm', name: '', api_url: '', api_key: '', model: '', dimension: 1024 })
const profileDialogTitle = computed(() =>
  (editingProfile.value ? '编辑' : '新增') + (profileForm.type === 'llm' ? ' LLM 档案' : ' Embedding 档案'))

// ── 高级配置 ──
const configs = ref([])
const loadingConfigs = ref(false)
const showAdd = ref(false)
const showEdit = ref(false)
const savingConfig = ref(false)
const editTarget = ref(null)
const addForm = reactive({ config_key: '', config_value: '', description: '' })
const editForm = reactive({ config_key: '', config_value: '', description: '' })

onMounted(() => {
  fetchSettings()
  fetchProfiles()
  fetchConfigs()
})

async function fetchSettings() {
  try {
    const res = await getSettings()
    if (res.code === 200) {
      Object.assign(settings.llm, res.data.llm)
      Object.assign(settings.embedding, res.data.embedding)
      Object.assign(settings.retrieval, res.data.retrieval)
      Object.assign(llmForm, {
        api_base: settings.llm.api_base, model: settings.llm.model, api_key: '',
        temperature: settings.llm.temperature, top_p: settings.llm.top_p, max_tokens: settings.llm.max_tokens,
      })
      Object.assign(embForm, {
        api_base: settings.embedding.api_base, model: settings.embedding.model, api_key: '',
        dimension: settings.embedding.dimension,
      })
      Object.assign(retrievalForm, settings.retrieval)
    }
  } catch { /* ignore */ }
}

async function saveLlm() {
  savingLlm.value = true
  try {
    const payload = {
      llm_api_base: llmForm.api_base, llm_model: llmForm.model,
      temperature: llmForm.temperature, top_p: llmForm.top_p, max_tokens: llmForm.max_tokens,
    }
    if (llmForm.api_key) payload.llm_api_key = llmForm.api_key
    await saveSettings(payload)
    ElMessage.success('LLM 设置已保存')
    fetchSettings()
  } catch { ElMessage.error('保存失败') } finally { savingLlm.value = false }
}

async function saveEmbedding() {
  savingEmb.value = true
  try {
    const payload = {
      embedding_api_base: embForm.api_base, embedding_model: embForm.model, embedding_dimension: embForm.dimension,
    }
    if (embForm.api_key) payload.embedding_api_key = embForm.api_key
    await saveSettings(payload)
    ElMessage.success('Embedding 设置已保存')
    fetchSettings()
  } catch { ElMessage.error('保存失败') } finally { savingEmb.value = false }
}

async function saveRetrieval() {
  savingRetrieval.value = true
  try {
    await saveSettings({ retrieval: { ...retrievalForm } })
    ElMessage.success('检索设置已保存')
    fetchSettings()
  } catch { ElMessage.error('保存失败') } finally { savingRetrieval.value = false }
}

// 拉取模型列表：target = 'llm' | 'embedding' | 'profile'
async function fetchInto(target) {
  const flagMap = { llm: llmFetching, embedding: embFetching, profile: profileFetching }
  const listMap = { llm: llmModels, embedding: embModels, profile: profileModels }
  let apiUrl, apiKey, modelType, profileId, useSaved
  if (target === 'profile') {
    apiUrl = profileForm.api_url; apiKey = profileForm.api_key; modelType = profileForm.type
    profileId = editingProfile.value?.id; useSaved = !profileForm.api_key && !!editingProfile.value
  } else if (target === 'llm') {
    apiUrl = llmForm.api_base; apiKey = llmForm.api_key; modelType = 'llm'; useSaved = !llmForm.api_key
  } else {
    apiUrl = embForm.api_base; apiKey = embForm.api_key; modelType = 'embedding'; useSaved = !embForm.api_key
  }
  if (!apiUrl) { ElMessage.warning('请先填写 API Base URL'); return }
  flagMap[target].value = true
  try {
    const res = await fetchModels({ api_url: apiUrl, api_key: apiKey || '', model_type: modelType, profile_id: profileId, use_saved_key: useSaved })
    if (res.code === 200 && !res.data.error) {
      listMap[target].value = res.data.models || []
      if (!res.data.models?.length) ElMessage.info('该服务未返回模型列表，可手动输入模型名')
      else ElMessage.success(`拉取到 ${res.data.models.length} 个模型`)
    } else {
      ElMessage.error(res.data?.error || '拉取失败')
    }
  } catch { ElMessage.error('拉取失败') } finally { flagMap[target].value = false }
}

// ── 档案 ──
async function fetchProfiles() {
  try {
    const res = await getProfiles()
    if (res.code === 200) profiles.value = res.data
  } catch { /* ignore */ }
}

function openProfile(type, row = null) {
  editingProfile.value = row
  profileModels.value = []
  Object.assign(profileForm, {
    type, name: row?.name || '', api_url: row?.api_url || '', api_key: '',
    model: row?.model || '', dimension: row?.dimension || 1024,
  })
  profileVisible.value = true
}

async function saveProfile() {
  if (!profileForm.name || !profileForm.api_url || !profileForm.model) {
    ElMessage.warning('请填写名称、API 地址和模型'); return
  }
  savingProfile.value = true
  try {
    if (editingProfile.value) {
      const payload = { name: profileForm.name, api_url: profileForm.api_url, model: profileForm.model }
      if (profileForm.type === 'embedding') payload.dimension = profileForm.dimension
      if (profileForm.api_key) payload.api_key = profileForm.api_key
      await updateProfile(editingProfile.value.id, payload)
    } else {
      const payload = {
        type: profileForm.type, name: profileForm.name, api_url: profileForm.api_url,
        model: profileForm.model, api_key: profileForm.api_key || null,
      }
      if (profileForm.type === 'embedding') payload.dimension = profileForm.dimension
      await createProfile(payload)
    }
    ElMessage.success('已保存')
    profileVisible.value = false
    fetchProfiles()
    fetchSettings()
  } catch { ElMessage.error('保存失败') } finally { savingProfile.value = false }
}

async function activate(row) {
  try {
    await activateProfile(row.id)
    ElMessage.success('已切换为当前使用配置')
    fetchProfiles()
    fetchSettings()
  } catch { ElMessage.error('切换失败') }
}

async function removeProfile(row) {
  try {
    await ElMessageBox.confirm(`确定删除档案「${row.name}」？`, '提示')
    await deleteProfile(row.id)
    ElMessage.success('已删除')
    fetchProfiles()
  } catch { /* cancelled */ }
}

// ── 高级配置 ──
async function fetchConfigs() {
  loadingConfigs.value = true
  try {
    const res = await getConfigs()
    if (res.code === 200) configs.value = res.data
  } finally { loadingConfigs.value = false }
}

async function addConfig() {
  if (!addForm.config_key || !addForm.config_value) { ElMessage.warning('请填写配置键和值'); return }
  savingConfig.value = true
  try {
    await createConfig({ ...addForm })
    ElMessage.success('已创建')
    showAdd.value = false
    Object.assign(addForm, { config_key: '', config_value: '', description: '' })
    fetchConfigs(); fetchSettings()
  } catch { ElMessage.error('创建失败') } finally { savingConfig.value = false }
}

function editConfig(row) {
  editTarget.value = row
  Object.assign(editForm, { config_key: row.config_key, config_value: row.config_value, description: row.description })
  showEdit.value = true
}

async function saveEditConfig() {
  savingConfig.value = true
  try {
    await updateConfig(editTarget.value.id, { config_value: editForm.config_value, description: editForm.description })
    ElMessage.success('已更新')
    showEdit.value = false
    fetchConfigs(); fetchSettings()
  } catch { ElMessage.error('更新失败') } finally { savingConfig.value = false }
}

async function removeConfig(row) {
  try {
    await ElMessageBox.confirm('确定删除此配置？', '提示')
    await deleteConfig(row.id)
    ElMessage.success('已删除')
    fetchConfigs()
  } catch { /* cancelled */ }
}
</script>

<style scoped>
.page-toolbar { display:flex; align-items:baseline; gap:16px; margin-bottom:20px; flex-wrap:wrap; }
.page-toolbar h2 { margin:0; }
.toolbar-hint { font-size:12px; color:var(--text3); }
.section-card { margin-bottom:20px; }
.card-title { font-size:15px; font-weight:600; }
.card-head-flex { display:flex; justify-content:space-between; align-items:center; }
.field-hint { font-size:12px; color:var(--text2); }
.model-row { display:flex; gap:8px; width:100%; }
.param-row { display:flex; align-items:center; gap:8px; flex-wrap:wrap; font-size:13px; color:var(--text2); }
</style>
