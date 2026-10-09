import { apiUrl } from './apiConfig'
import type { AuthResponse, RegisterInput, UserProfile, StudentMenuItem, StudentOrder, OrderTracking, StudentNotification, WalletTransaction, WalletTopup } from './studentTypes'

const TOKEN_KEY = 'sco_fastapi_student_token'
export const usesStudentCookieSession = import.meta.env.VITE_NATIVE_APP !== 'true' && import.meta.env.VITE_AUTH_COOKIE_MODE === 'true'
let sessionVersion = 0
export const STUDENT_SESSION_EXPIRED = 'sco:student-session-expired'

export class StudentApiError extends Error {
  constructor(message: string, public status: number) { super(message); this.name = 'StudentApiError' }
}
function getToken(): string | null {
  if (usesStudentCookieSession) return null
  try { return sessionStorage.getItem(TOKEN_KEY) } catch { return null }
}
function setToken(token: string | null) {
  sessionVersion++
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token)
    else sessionStorage.removeItem(TOKEN_KEY)
  } catch { if (token) throw new StudentApiError('Allow session storage in your browser to sign in.', 0) }
  try {
    // Legacy profile caching is never used to authorize a student session.
    localStorage.removeItem('sco_auth_token')
    localStorage.removeItem('sco_auth_user')
  } catch { /* Private browsing may restrict local storage independently of session storage. */ }
}
async function request<T>(path: string, method = 'GET', body?: unknown, authenticated = true, extraHeaders: Record<string, string> = {}): Promise<T> {
  const token = authenticated ? getToken() : null
  const version = sessionVersion
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 20000)
  try {
    if (import.meta.env.VITE_NATIVE_APP === 'true' && import.meta.env.VITE_ANDROID_BACKEND_PLACEHOLDER === 'true') {
      throw new StudentApiError('Staging backend is not configured. Ask the canteen to deploy its HTTPS backend and rebuild this app.', 0)
    }
    const res = await fetch(apiUrl(`/api${path}`), {
      method, cache: 'no-store', credentials: usesStudentCookieSession ? 'include' : 'omit', signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...extraHeaders,
        ...(!authenticated && method === 'POST' && usesStudentCookieSession ? { 'X-Session-Mode': 'cookie' } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    })
    const data = await res.json().catch(() => null)
    if (!res.ok) {
      if (authenticated && (token || usesStudentCookieSession) && (res.status === 401 || res.status === 403) && version === sessionVersion && (usesStudentCookieSession || getToken() === token)) {
        setToken(null)
        window.dispatchEvent(new Event(STUDENT_SESSION_EXPIRED))
      }
      const detail = data?.detail
      const message = typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((e: { msg?: string }) => e.msg).filter(Boolean).join('. ') : data?.message
      throw new StudentApiError(message || `Request failed (${res.status}). Please try again.`, res.status)
    }
    if (data === null && res.status !== 204) throw new StudentApiError('The canteen returned an invalid response.', 502)
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
    if (data.success) {
      if (!data.user || (!usesStudentCookieSession && !data.token)) throw new StudentApiError('The server returned an invalid sign-in response.', 502)
      setToken(usesStudentCookieSession ? null : data.token!)
    }
    return data
  } catch (error) { return { success: false, message: (error as Error).message } }
}

export const apiClient = {
  getToken,
  hasSession: () => usesStudentCookieSession || Boolean(getToken()),
  login: (rollNumber: string, passcode: string) => authenticate('/auth/login', { rollNumber, passcode }),
  register: (input: RegisterInput) => authenticate('/auth/register', input),
  getMe: () => request<{ success: boolean; user?: UserProfile }>('/auth/me'),
  async logout() {
    const pendingLogout = (usesStudentCookieSession || getToken()) ? request('/auth/logout', 'POST') : Promise.resolve()
    setToken(null)
    try { await pendingLogout } catch { /* Local logout must also work while disconnected. */ }
  },
  requestPasscodeReset: (rollNumber: string) => request<{ success: boolean; message: string; otp?: string }>('/auth/forgot-passcode', 'POST', { rollNumber }, false),
  async resetPasscode(rollNumber: string, otp: string, newPasscode: string) {
    const result = await request<{ success: boolean; message: string }>('/auth/reset-passcode', 'POST', { rollNumber, otp, newPasscode }, false)
    if (result.success) setToken(null)
    return result
  },
  getMenu: () => request<StudentMenuItem[]>('/menu/items', 'GET', undefined, false),
  getMenuItem: (id: string) => request<StudentMenuItem>(`/menu/items/${encodeURIComponent(id)}`, 'GET', undefined, false),
  getOrders: () => request<StudentOrder[]>('/student/orders'),
  getOrder: (id: number) => request<StudentOrder>(`/student/orders/${id}`),
  getTracking: (id: number) => request<OrderTracking>(`/student/orders/${id}/tracking`),
  createOrder: (items: { id: string; qty: number }[], paymentMethod: string, idempotencyKey: string) => request<StudentOrder>('/student/orders', 'POST', { items, paymentMethod }, true, { 'Idempotency-Key': idempotencyKey }),
  getPaymentsConfig: () => request<{ provider: 'disabled' | 'razorpay'; enabled: boolean }>('/student/payments/config'),
  verifyPayment: (id: number, payment: { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string }) => request<StudentOrder>('/student/orders/' + id + '/payment/verify', 'POST', payment),
  pickupOrder: (id: number) => request<StudentOrder>(`/student/orders/${id}/pickup`, 'POST'),
  getNotifications: () => request<StudentNotification[]>('/student/notifications'),
  markAllNotificationsRead: () => request('/student/notifications/mark-all-read', 'POST'),
  getWallet: () => request<Pick<UserProfile, 'walletBalance' | 'upiId' | 'totalSpent' | 'totalOrders'>>('/student/wallet'),
  getWalletTransactions: () => request<WalletTransaction[]>('/student/wallet/transactions'),
  rechargeWallet: (amount: number, idempotencyKey: string) => request<WalletTopup>('/student/wallet/recharge', 'POST', { amount, paymentMethod: 'razorpay' }, true, { 'Idempotency-Key': idempotencyKey }),
  getWalletTopups: () => request<WalletTopup[]>('/student/wallet/topups'),
  getWalletTopup: (id: number) => request<WalletTopup>('/student/wallet/topups/' + id),
  verifyWalletTopup: (id: number, payment: { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string }) => request<WalletTopup>('/student/wallet/topups/' + id + '/verify', 'POST', payment),

}
