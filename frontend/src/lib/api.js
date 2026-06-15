/**
 * frontend/src/lib/api.js
 * 
 * Typed API client for the FastAPI backend.
 * Automatically injects the Supabase JWT into every request.
 * All errors are normalized to { error: string } shape.
 */

import { supabase } from './supabase'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

async function getAuthHeader() {
  const { data: { session } } = await supabase.auth.getSession()
  if (!session?.access_token) {
    throw new Error('Not authenticated')
  }
  return { Authorization: `Bearer ${session.access_token}` }
}

async function request(method, path, body = null, params = {}) {
  const authHeader = await getAuthHeader()
  
  // Build query string
  const queryString = Object.entries(params)
    .filter(([, v]) => v !== null && v !== undefined)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&')
  
  const url = `${API_URL}${path}${queryString ? '?' + queryString : ''}`
  
  const options = {
    method,
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'no-cache, no-store, must-revalidate',
      'Pragma': 'no-cache',
      ...authHeader,
    },
  }
  
  if (body) {
    options.body = JSON.stringify(body)
  }
  
  const resp = await fetch(url, options)
  
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ error: resp.statusText }))
    throw new Error(err.error || `Request failed: ${resp.status}`)
  }
  
  return resp.json()
}

async function uploadFile(path, file, params = {}) {
  const authHeader = await getAuthHeader()
  const queryString = Object.entries(params)
    .filter(([, v]) => v !== null && v !== undefined)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&')
  
  const url = `${API_URL}${path}${queryString ? '?' + queryString : ''}`
  const formData = new FormData()
  formData.append('file', file)
  
  const resp = await fetch(url, {
    method: 'POST',
    headers: authHeader,
    body: formData,
  })
  
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ error: resp.statusText }))
    throw new Error(err.error || `Upload failed: ${resp.status}`)
  }
  
  return resp.json()
}

// ── Jobs API ──────────────────────────────────────────────────
export const jobsApi = {
  list: (params = {}) => request('GET', '/api/jobs/', null, params),
  updateStatus: (matchId, status) =>
    request('PATCH', `/api/jobs/${matchId}/status`, { status }),
}

// ── Profile API ───────────────────────────────────────────────
export const profileApi = {
  get: () => request('GET', '/api/profile/'),
  update: (data) => request('PATCH', '/api/profile/', data),
  uploadResume: (file) => uploadFile('/api/profile/resume', file),
  generateDescription: (skills, seniorityLevels) => 
    request('POST', '/api/profile/generate_description', { 
      skills, 
      seniority_levels: seniorityLevels 
    }),
}

// ── Sources API ───────────────────────────────────────────────
export const sourcesApi = {
  getAll: () => request('GET', '/api/sources/'),
  getLibrary: (category) => request('GET', '/api/sources/library', null, category ? { category } : {}),
  getCategories: () => request('GET', '/api/sources/categories'),
  toggle: (sourceId, isActive) =>
    request('PATCH', `/api/sources/${sourceId}/toggle`, { is_active: isActive }),
}

// ── Imports API ───────────────────────────────────────────────
export const importsApi = {
  bulk: (rawUrls) => request('POST', '/api/imports/bulk', { raw_urls: rawUrls }),
  activate: (sources) => request('POST', '/api/imports/activate', { sources }),
  github: (repoUrl) => request('POST', '/api/imports/github', { repo_url: repoUrl }),
}

// ── Telegram API ──────────────────────────────────────────────
export const telegramApi = {
  verify: (code) => request('POST', '/api/telegram/verify', { code }),
  unlink: () => request('DELETE', '/api/telegram/unlink'),
  status: () => request('GET', '/api/telegram/status'),
}
