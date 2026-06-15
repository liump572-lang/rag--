import request from './request'

// ── 当前生效配置（LLM / Embedding / 检索） ──
export function getSettings() {
  return request.get('/admin/system/settings')
}

export function saveSettings(data) {
  return request.put('/admin/system/settings', data)
}

export function getApiKeyStatus() {
  return request.get('/admin/system/apikey-status')
}

// ── 模型档案 ──
export function getProfiles() {
  return request.get('/admin/system/profiles')
}

export function createProfile(data) {
  return request.post('/admin/system/profiles', data)
}

export function updateProfile(id, data) {
  return request.put(`/admin/system/profiles/${id}`, data)
}

export function deleteProfile(id) {
  return request.delete(`/admin/system/profiles/${id}`)
}

export function activateProfile(id) {
  return request.post(`/admin/system/profiles/${id}/activate`)
}

export function fetchModels(data) {
  return request.post('/admin/system/fetch-models', data)
}

// ── 通用配置 ──
export function getConfigs(params) {
  return request.get('/admin/system/configs', { params })
}

export function createConfig(data) {
  return request.post('/admin/system/configs', data)
}

export function updateConfig(id, data) {
  return request.put(`/admin/system/configs/${id}`, data)
}

export function deleteConfig(id) {
  return request.delete(`/admin/system/configs/${id}`)
}
