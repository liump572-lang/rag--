import request from './request'

export function getSubgraph(params) {
  return request.get('/kg/subgraph', { params })
}

export function searchKnowledge(params) {
  return request.get('/kg/search', { params })
}

export function getPoints(params) {
  return request.get('/kg/points', { params })
}

export function createPoint(data) {
  return request.post('/kg/points', data)
}

export function updatePoint(id, data) {
  return request.put(`/kg/points/${id}`, data)
}

export function deletePoint(id) {
  return request.delete(`/kg/points/${id}`)
}

export function getRelations(params) {
  return request.get('/kg/relations', { params })
}

export function createRelation(data) {
  return request.post('/kg/relations', data)
}

export function updateRelation(id, data) {
  return request.put(`/kg/relations/${id}`, data)
}

export function deleteRelation(id) {
  return request.delete(`/kg/relations/${id}`)
}

export function searchSubgraph(params) {
  return request.get('/kg/search-subgraph', { params })
}

export function generateDocument(data) {
  return request.post('/kg/generate-document', data)
}

export function getRebuildStatus() {
  return request.get('/kg/rebuild/status')
}

export function getDocumentExtractionStatus(params) {
  return request.get('/kg/documents/status', { params })
}

export function retryFailedRebuildDocuments() {
  return request.post('/kg/rebuild/retry-failed')
}

export function getRelationCandidates(params) {
  return request.get('/kg/relation-candidates', { params })
}

export function approveRelationCandidate(id) {
  return request.post(`/kg/relation-candidates/${id}/approve`)
}

export function rejectRelationCandidate(id) {
  return request.post(`/kg/relation-candidates/${id}/reject`)
}
