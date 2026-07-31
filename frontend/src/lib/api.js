const BASE_URL = import.meta.env.VITE_API_URL
const CLIENT_ID = 'samara'
const TOKEN_KEY = 'samara_dashboard_token'

let _token = localStorage.getItem(TOKEN_KEY)

export const setToken = (t) => {
  _token = t
  if (t) localStorage.setItem(TOKEN_KEY, t)
  else localStorage.removeItem(TOKEN_KEY)
}
export const clearToken = () => {
  _token = null
  localStorage.removeItem(TOKEN_KEY)
}
export const getToken = () => _token || localStorage.getItem(TOKEN_KEY)

const withClientId = (params = new URLSearchParams()) => {
  params.set('client_id', CLIENT_ID)
  return params
}

const api = async (url, method = 'GET', body = null) => {
  const token = getToken()
  const options = {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  }
  if (body) options.body = JSON.stringify(body)

  const res = await fetch(`${BASE_URL}${url}`, options)

  if (res.status === 401 || res.status === 403) {
    clearToken()
    if (window.location.pathname !== '/login') {
      window.location.href = '/login'
    }
    throw new Error('Unauthorized')
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || 'Request failed')
  }
  if (res.status === 204) return null
  return res.json()
}

// ---------------- SYSTEM ----------------
export const login = (data) => api('/system/auth/login', 'POST', data)
export const logout = () => { clearToken(); return Promise.resolve() }
export const pingAPI = () => api('/system/ping')

// ---------------- DASHBOARD ----------------
export const getDashboardStats = ({ period, start_date, end_date } = {}) => {
  const q = withClientId()
  if (period && period !== 'all') q.set('period', period)
  if (start_date) q.set('start_date', start_date)
  if (end_date) q.set('end_date', end_date)
  return api(`/system/dashboard/stats?${q.toString()}`)
}

export const getDashboardRatings = () => {
  const q = withClientId()
  return api(`/system/dashboard/ratings?${q.toString()}`)
}

export const getUserGrowth = (period = 'month') => {
  const q = withClientId()
  q.set('period', period)
  return api(`/system/dashboard/users/growth?${q.toString()}`)
}

export const getModelMix = (days = 7) => {
  const q = withClientId()
  q.set('days', String(days))
  return api(`/system/dashboard/model-mix?${q.toString()}`)
}

// ---------------- USERS ----------------
export const listUsers = (page = 1, limit = 20, agentRequested = false) => {
  const q = withClientId()
  q.set('page', String(page))
  q.set('limit', String(limit))
  if (agentRequested) q.set('agent_requested', 'true')
  return api(`/system/user?${q.toString()}`).then(res => ({
    users: res?.results ?? res?.users ?? [],
    total: res?.total ?? 0,
    page: res?.page,
    limit: res?.limit,
  }))
}

export const searchUsers = (query, limit = 20) => {
  const q = withClientId()
  q.set('q', query)
  q.set('limit', String(limit))
  return api(`/system/user/search?${q.toString()}`)
}

export const getUserByPhone = (phone) => {
  const q = withClientId()
  return api(`/system/user/${phone}?${q.toString()}`)
}

export const resetUser = (phone) => {
  const q = withClientId()
  return api(`/system/user/${phone}/reset?${q.toString()}`, 'POST')
}

export const deleteUserChat = (phone) => {
  const q = withClientId()
  return api(`/system/user/${phone}/delete-chat?${q.toString()}`, 'POST')
}

/** Admin bypass — grant credits without Razorpay (default 10). */
export const grantUserCredits = (phone, amount = 10) => {
  const q = withClientId()
  q.set('amount', String(amount))
  return api(`/system/user/${phone}/grant-credits?${q.toString()}`, 'POST')
}

/** Hard-delete user + related Mongo rows for a fresh WhatsApp start. */
export const deleteUserFully = (phone) => {
  const q = withClientId()
  return api(`/system/user/${phone}/delete?${q.toString()}`, 'POST')
}

export const getChatHistory = (phone, { before, beforeId, limit = 50 } = {}) => {
  const q = withClientId()
  q.set('limit', String(limit))
  if (before != null) q.set('before', String(before))
  if (beforeId) q.set('before_id', beforeId)
  return api(`/system/chat-history/${phone}?${q.toString()}`)
}

export const getMessageTrace = (requestId) => {
  const q = withClientId()
  return api(`/system/message-trace/${requestId}?${q.toString()}`)
}

// ---------------- CONVERSATIONS ----------------
export const takeoverConversation = (phone, takenBy) =>
  api(`/system/conversation/${phone}/takeover`, 'POST', { taken_by: takenBy })

export const sendAgentMessage = (phone, message) =>
  api(`/system/conversation/${phone}/send`, 'POST', { message })

export const releaseConversation = (phone) =>
  api(`/system/conversation/${phone}/release`, 'POST')

export const resolveAgentRequest = (phone) =>
  api(`/system/conversation/${phone}/resolve-agent`, 'POST')
