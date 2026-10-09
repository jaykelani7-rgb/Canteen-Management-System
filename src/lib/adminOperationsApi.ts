import { adminRequest, usesAdminCookieSession } from './adminApi'
import { apiUrl } from './apiConfig'
import type { StudentMenuItem, StudentOrder } from './studentTypes'
export type AdminOrder = StudentOrder & { studentName: string; rollNumber: string }
export type CatalogueItem = StudentMenuItem & { timingWindow: string; ordersToday?: number }
export interface WeeklyMeal { day: string; meal_type: 'breakfast' | 'lunch' | 'snacks' | 'dinner'; items: string[] }
export interface PaymentReconciliation {
  paymentIntentId: number; orderId: number | null; purpose: 'order' | 'wallet_topup'; state: string;
  amountPaise: number; currency: string; receipt: string; providerOrderId: string | null;
  providerPaymentId: string | null; refundId: string | null; refundStatus: string | null; unrecoveredRefundPaise: number; createdAt?: string;
}
export interface AdminAnalytics {
  dailyRevenue: number; activeStudents: number; totalOrders: number; activeOrders: number; yesterdayRevenue: number
  topItems: { name: string; quantity: number; revenue: number }[]
  redisCacheHitPercent: number | null; wasteReductionPercent: number | null
}
export const adminOperationsApi = {
  reconciliation: () => adminRequest<PaymentReconciliation[]>('/payments/reconciliation'),
  reconcileIntent: (id: number, providerOrderId?: string) => adminRequest<unknown>('/payments/intents/' + id + '/reconcile', 'POST', providerOrderId ? { providerOrderId } : {}),
  refundIntent: (id: number, reason: string) => adminRequest<unknown>('/payments/intents/' + id + '/refund', 'POST', { reason }),
  refundOrder: (id: number, reason: string) => adminRequest<unknown>('/payments/' + id + '/refund', 'POST', { reason }),
  orders: (status?: string) => adminRequest<AdminOrder[]>('/orders' + (status && status !== 'All' ? '?status=' + encodeURIComponent(status) : '')),
  setOrderStatus: (id: number, status: string, reason?: string) => adminRequest<StudentOrder>('/orders/' + id + '/status', 'POST', { status, ...(reason ? { cancellationReason: reason } : {}) }),
  operations: () => adminRequest<{ serviceOnline: boolean; pendingOrders: number; activeWindow: string; redisAvailable: boolean }>('/operations/status'),
  analytics: () => adminRequest<AdminAnalytics>('/analytics'),
  catalogue: () => adminRequest<CatalogueItem[]>('/catalogue'),
  createItem: (item: Omit<CatalogueItem, 'id' | 'rating' | 'ordersToday'>) => adminRequest<CatalogueItem>('/catalogue', 'POST', item),
  updateItem: (id: string, item: Partial<CatalogueItem>) => adminRequest<CatalogueItem>('/catalogue/' + encodeURIComponent(id), 'PUT', item),
  availability: (id: string, available: boolean) => adminRequest<CatalogueItem>('/catalogue/' + encodeURIComponent(id) + '/availability', 'PATCH', { available }),
  removeItem: (id: string) => adminRequest<CatalogueItem>('/catalogue/' + encodeURIComponent(id), 'DELETE'),
  extractMenu: (file: File) => { const body = new FormData(); body.append('file', file); return adminRequest<{ schedule: WeeklyMeal[] }>('/menu/upload-ocr', 'POST', body) },
  saveWeeklyMenu: (schedule: WeeklyMeal[]) => adminRequest<{ schedule: WeeklyMeal[] }>('/menu/weekly', 'POST', { schedule }),
  async weeklyMenu(): Promise<unknown> {
    const response = await fetch(apiUrl('/api/menu/weekly'), { cache: 'no-store', credentials: usesAdminCookieSession ? 'include' : 'omit', signal: AbortSignal.timeout(20000) })
    const body = await response.json().catch(() => null)
    if (!response.ok || !body) throw new Error(typeof body?.detail === 'string' ? body.detail : 'Cannot load the weekly menu.')
    return body
  },
}
