const TOKEN_KEY = 'wpr_auth_token'
const COOKIE_NAME = 'wpr_token'
const SESSION_SECONDS = 60 * 60 * 24 // 24h

export interface LoginResult {
  ok: boolean
  error?: string
}

interface JwtPayload {
  email?: string
  exp?: number
}

function decodePayload(token: string): JwtPayload | null {
  try {
    const payload = token.split('.')[1]
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'))
    return JSON.parse(json) as JwtPayload
  } catch {
    return null
  }
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token)
  const secure = location.protocol === 'https:' ? '; Secure' : ''
  document.cookie = `${COOKIE_NAME}=${token}; path=/; max-age=${SESSION_SECONDS}; SameSite=Lax${secure}`
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
  document.cookie = `${COOKIE_NAME}=; path=/; max-age=0; SameSite=Lax`
}

export function isAuthenticated(): boolean {
  const token = getToken()
  if (!token) return false
  const payload = decodePayload(token)
  if (!payload?.exp) return false
  return payload.exp * 1000 > Date.now()
}

export async function login(email: string, password: string): Promise<LoginResult> {
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  const data = await res.json().catch(() => ({}))

  if (!res.ok || !data.token) {
    return { ok: false, error: data.error ?? 'No se pudo iniciar sesión' }
  }

  setToken(data.token)
  return { ok: true }
}

export function logout() {
  clearToken()
  window.location.href = '/login'
}
