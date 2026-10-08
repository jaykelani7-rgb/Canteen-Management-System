import { apiUrl } from './apiConfig'
import type { AuthResponse, RegisterInput, UserProfile, StudentMenuItem, StudentOrder, OrderTracking, StudentNotification, WalletTransaction } from './studentTypes'

const TOKEN_KEY = 'sco_fastapi_student_token'
export const STUDENT_SESSION_EXPIRED = 'sco:student-session-expired'

export class StudentApiError extends Error {
  constructor(message: string, public status: number) { super(message); this.name = 'StudentApiError' }
}
function getToken(): string | null {
  try { return sessionStorage.getItem(TOKEN_KEY) } catch { return null }
}
function setToken(token: string | null) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token)
    else sessionStorage.removeItem(TOKEN_KEY)
    // Remove the former prototype's cached profile and non-JWT session.
    localStorage.removeItem('sco_auth_token')
    localStorage.removeItem('sco_auth_user')
  } catch { /* Browsers may restrict storage. Authentication will be required again. */ }
}
async function request<T>(path: string, method = 'GET', body?: unknown, authenticated = true): Promise<T> {
  const token = authenticated ? getToken() : null
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 20000)
  try {
    const res = await fetch(apiUrl(`/api${path}`), {
      method, cache: 'no-store', signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    })
    const data = await res.json().catch(() => null)
    if (!res.ok) {
      if (authenticated && token && (res.status === 401 || res.status === 403) && getToken() === token) {
        setToken(null)
        window.dispatchEvent(new Event(STUDENT_SESSION_EXPIRED))
      }
      const detail = data?.detail
      const message = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((e: { msg?: string }) => e.msg).filter(Boolean).join('. ') : data?.message
      throw new StudentApiError(message || `Request failed (${res.status}). Please try again.`, res.status)
    }
    return data as T
  } catch (error) {
    if (error instanceof StudentApiError) throw error
    throw new StudentApiError(method === 'POST' && path === '/student/orders'
      ? 'Could not confirm the order response. Check Your Orders before trying again.'
      : 'Cannot reach the canteen. Check your connection and try again.', 0)
  } finally { clearTimeout(timer) }
}
async function authenticate(path: string, input: unknown): Promise<AuthResponse> {
  try {
    const data = await request<AuthResponse>(path, 'POST', input, false)
    if (data.success && data.token && data.user) setToken(data.token)
    return data
  } catch (error) { return { success: false, message: (error as Error).message } }
}

export const apiClient = {
  getToken,
  login: (rollNumber: string, passcode: string) => authenticate('/auth/login', { rollNumber, passcode }),
  register: (input: RegisterInput) => authenticate('/auth/register', input),
  getMe: () => request<{ success: boolean; user?: UserProfile }>('/auth/me'),
  async logout() {
    const pendingLogout = getToken() ? request('/auth/logout', 'POST') : Promise.resolve()
    setToken(null)
    try { await pendingLogout } catch { /* Local logout must also work while disconnected. */ }
  },
  requestPasscodeReset: (rollNumber: string) => request<{ success: boolean; message: string; otp?: string }>('/auth/forgot-passcode', 'POST', { rollNumber }, false),
  resetPasscode: (rollNumber: string, otp: string, newPasscode: string) => authenticate('/auth/reset-passcode', { rollNumber, otp, newPasscode }),
  getMenu: () => request<StudentMenuItem[]>('/menu/items', 'GET', undefined, false),
  getMenuItem: (id: string) => request<StudentMenuItem>(`/menu/items/${encodeURIComponent(id)}`, 'GET', undefined, false),
  getOrders: () => request<StudentOrder[]>('/student/orders'),
  getOrder: (id: number) => request<StudentOrder>(`/student/orders/${id}`),
  getTracking: (id: number) => request<OrderTracking>(`/student/orders/${id}/tracking`),
  createOrder: (items: StudentOrder['items'], paymentMethod: string) => request<StudentOrder>('/student/orders', 'POST', { items, paymentMethod }),
  pickupOrder: (id: number) => request<StudentOrder>(`/student/orders/${id}/pickup`, 'POST'),
  getNotifications: () => request<StudentNotification[]>('/student/notifications'),
  markAllNotificationsRead: () => request('/student/notifications/mark-all-read', 'POST'),
  getWallet: () => request<Pick<UserProfile, 'walletBalance' | 'upiId' | 'totalSpent' | 'totalOrders'>>('/student/wallet'),
  getWalletTransactions: () => request<WalletTransaction[]>('/student/wallet/transactions'),
  rechargeWallet: (amount: number) => request<{ success: boolean; message: string; walletBalance: number }>('/student/wallet/recharge', 'POST', { amount, paymentMethod: 'UPI' }),
}
