import { apiUrl } from './apiConfig'

export interface AdminUser { id: number; username: string; role: string; is_active: boolean }

export class AdminApiError extends Error {
  constructor(message: string, public status: number) { super(message); this.name = 'AdminApiError' }
}

const TOKEN_KEY = 'sco_fastapi_admin_token'
const SESSION_EVENT = 'sco-admin-session-ended'

export function getAdminToken(): string | null {
  try { return sessionStorage.getItem(TOKEN_KEY) } catch { return null }
}

export function clearAdminToken(message = '') {
  try { sessionStorage.removeItem(TOKEN_KEY) } catch { /* The gate still closes when browser storage is unavailable. */ }
  window.dispatchEvent(new CustomEvent(SESSION_EVENT, { detail: message }))
}

export function onAdminSessionEnded(listener: (message: string) => void) {
  const handle = (event: Event) => listener((event as CustomEvent<string>).detail || '')
  window.addEventListener(SESSION_EVENT, handle)
  return () => window.removeEventListener(SESSION_EVENT, handle)
}

export async function adminRequest<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const token = path === '/login' ? null : getAdminToken()
  let response: Response
  try {
    response = await fetch(apiUrl(`/api/admin${path}`), {
      method,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(15000),
    })
  } catch { throw new AdminApiError('Cannot reach the backend. Check that FastAPI is running, then try again.', 0) }
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const message = typeof data?.detail === 'string' ? data.detail : Array.isArray(data?.detail)
      ? data.detail.map((item: { msg: string }) => item.msg).join('; ')
      : response.status >= 500 ? 'The backend is unavailable. Please try again shortly.' : 'The request could not be completed.'
    if (token && (response.status === 401 || response.status === 403) && getAdminToken() === token) {
      clearAdminToken(message)
    }
    throw new AdminApiError(message, response.status)
  }
  return data as T
}

export async function adminLogin(username: string, password: string) {
  const result = await adminRequest<{ access_token: string }>('/login', 'POST', { username, password })
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

export function adminLogout() { clearAdminToken() }
