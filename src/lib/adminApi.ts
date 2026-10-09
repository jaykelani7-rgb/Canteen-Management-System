import { apiUrl } from './apiConfig'

export interface AdminUser { id: number; username: string; role: string; is_active: boolean }
export class AdminApiError extends Error {
  constructor(message: string, public status: number) { super(message); this.name = 'AdminApiError' }
}
const TOKEN_KEY = 'sco_fastapi_admin_token'
const SESSION_EVENT = 'sco-admin-session-ended'
export const usesAdminCookieSession = import.meta.env.VITE_AUTH_COOKIE_MODE === 'true'
let sessionVersion = 0
export function getAdminToken(): string | null {
  if (usesAdminCookieSession) return null
  try { return sessionStorage.getItem(TOKEN_KEY) } catch { return null }
}
export function hasAdminSession() { return usesAdminCookieSession || Boolean(getAdminToken()) }
export function clearAdminToken(message = '') {
  sessionVersion++
  try { sessionStorage.removeItem(TOKEN_KEY) } catch { /* The gate still closes if storage is restricted. */ }
  window.dispatchEvent(new CustomEvent(SESSION_EVENT, { detail: message }))
}
export function onAdminSessionEnded(listener: (message: string) => void) {
  const handle = (event: Event) => listener((event as CustomEvent<string>).detail || '')
  window.addEventListener(SESSION_EVENT, handle)
  return () => window.removeEventListener(SESSION_EVENT, handle)
}
export async function adminRequest<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const authenticating = path === '/login'
  const token = authenticating ? null : getAdminToken()
  const version = sessionVersion
  const multipart = body instanceof FormData
  let response: Response
  try {
    response = await fetch(apiUrl('/api/admin' + path), {
      method, credentials: usesAdminCookieSession ? 'include' : 'omit', cache: 'no-store',
      headers: { ...(!multipart ? { 'Content-Type': 'application/json' } : {}),
        ...(token ? { Authorization: 'Bearer ' + token } : {}),
        ...(authenticating && usesAdminCookieSession ? { 'X-Session-Mode': 'cookie' } : {}) },
      body: body === undefined ? undefined : multipart ? body as FormData : JSON.stringify(body),
      signal: AbortSignal.timeout(multipart ? 60000 : 20000),
    })
  } catch { throw new AdminApiError('Cannot reach the backend. Check your connection, then try again.', 0) }
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const message = typeof data?.detail === 'string' ? data.detail : Array.isArray(data?.detail)
      ? data.detail.map((item: { msg: string }) => item.msg).join('; ')
      : response.status >= 500 ? 'The backend is unavailable. Please try again shortly.' : 'The request could not be completed.'
    if (!authenticating && (token || usesAdminCookieSession) && (response.status === 401 || response.status === 403) && version === sessionVersion && (usesAdminCookieSession || getAdminToken() === token)) clearAdminToken(message)
    throw new AdminApiError(message, response.status)
  }
  if (data === null && response.status !== 204) throw new AdminApiError('The backend returned an invalid response.', 502)
  return data as T
}
export async function adminLogin(username: string, password: string) {
  const result = await adminRequest<{ access_token?: string | null; token?: string | null }>('/login', 'POST', { username, password })
  sessionVersion++
  if (usesAdminCookieSession) {
    try { sessionStorage.removeItem(TOKEN_KEY) } catch { /* HttpOnly cookie authentication needs no browser token storage. */ }
    return
  }
  if (!result.access_token) throw new AdminApiError('The server returned an invalid sign-in response.', 502)
  try { sessionStorage.setItem(TOKEN_KEY, result.access_token) }
  catch { throw new AdminApiError('Allow session storage in your browser to sign in.', 0) }
}
export async function getAdminMe(): Promise<AdminUser> {
  const admin = await adminRequest<AdminUser>('/me')
  if (admin.role !== 'admin' || !admin.is_active) {
    clearAdminToken('An active administrator account is required.')
    throw new AdminApiError('An active administrator account is required.', 403)
  }
  return admin
}
export function adminLogout() {
  const pending = adminRequest('/logout', 'POST')
  clearAdminToken()
  void pending.catch(() => { /* Local logout also closes the workspace while disconnected. */ })
}
