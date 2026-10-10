import { adminRequest, usesAdminCookieSession, getAdminToken, clearAdminToken, AdminApiError } from './adminApi'
import { apiUrl } from './apiConfig'
import type { StudentMenuItem, StudentOrder } from './studentTypes'
export type AdminOrder = StudentOrder & { studentName: string; rollNumber: string }
export type CatalogueItem = StudentMenuItem & { timingWindow: string; ordersToday?: number; imageId?: string | null; imageConfirmed?: boolean; photoCredits?: string | null }
export interface FoodImageAsset {
  id: string; dishName: string; source: string; license: string; attribution: string;
  author?: string; licenseUrl?: string; modifications?: string;
  width: number; height: number; byteSize: number; mimeType: string; sha256: string;
  previewUrl: string; photo: string; createdAt: string;
}
export interface FoodImageUpload {
  file: File; dishName: string; source: string; license: string; attribution: string;
  author?: string; licenseUrl?: string; modifications?: string; rightsConfirmed: boolean;
}
type CatalogueInput = Omit<CatalogueItem, 'id' | 'rating' | 'ordersToday' | 'photo' | 'photoCredits'>

async function foodImageBlob(id: string, signal?: AbortSignal): Promise<Blob> {
  const token = getAdminToken(), controller = new AbortController()
  const cancel = () => controller.abort()
  signal?.addEventListener('abort', cancel, { once: true })
  if (signal?.aborted) controller.abort()
  const timeout = setTimeout(cancel, 20000)
  try {
    const response = await fetch(apiUrl('/api/admin/food-images/' + encodeURIComponent(id) + '/content'), {
      headers: token ? { Authorization: 'Bearer ' + token } : {}, cache: 'no-store',
      credentials: usesAdminCookieSession ? 'include' : 'omit', signal: controller.signal,
    })
    if (!response.ok) {
      const body = await response.json().catch(() => null)
      const message = typeof body?.detail === 'string' ? body.detail : 'Cannot load this image preview.'
      if ((response.status === 401 || response.status === 403) && (usesAdminCookieSession || (token && getAdminToken() === token))) clearAdminToken(message)
      throw new AdminApiError(message, response.status)
    }
    const blob = await response.blob()
    if (blob.type !== 'image/webp' || blob.size > 320 * 1024) throw new AdminApiError('The image preview is invalid.', 502)
    return blob
  } catch (cause) {
    if (cause instanceof AdminApiError || signal?.aborted) throw cause
    throw new AdminApiError('Cannot reach the image service. Check your connection and retry.', 0)
  } finally { clearTimeout(timeout); signal?.removeEventListener('abort', cancel) }
}
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
  createItem: (item: CatalogueInput) => adminRequest<CatalogueItem>('/catalogue', 'POST', item),
  updateItem: (id: string, item: Partial<CatalogueInput>) => adminRequest<CatalogueItem>('/catalogue/' + encodeURIComponent(id), 'PUT', item),
  availability: (id: string, available: boolean, imageConfirmed?: boolean) => adminRequest<CatalogueItem>('/catalogue/' + encodeURIComponent(id) + '/availability', 'PATCH', { available, ...(imageConfirmed === undefined ? {} : { imageConfirmed }) }),
  removeItem: (id: string) => adminRequest<CatalogueItem>('/catalogue/' + encodeURIComponent(id), 'DELETE'),
  foodImages: (query = '') => adminRequest<FoodImageAsset[]>('/food-images?limit=100&query=' + encodeURIComponent(query)),
  foodImage: (id: string) => adminRequest<FoodImageAsset>('/food-images/' + encodeURIComponent(id)),
  foodImageBlob,
  uploadFoodImage: (input: FoodImageUpload) => {
    const body = new FormData()
    body.append('file', input.file)
    for (const key of ['dishName', 'source', 'license', 'attribution', 'author', 'licenseUrl', 'modifications'] as const) if (input[key] !== undefined) body.append(key, input[key] || '')
    body.append('rightsConfirmed', String(input.rightsConfirmed))
    return adminRequest<FoodImageAsset>('/food-images', 'POST', body)
  },
  archiveFoodImage: (id: string) => adminRequest<unknown>('/food-images/' + encodeURIComponent(id), 'DELETE'),
  extractMenu: (file: File) => { const body = new FormData(); body.append('file', file); return adminRequest<{ schedule: WeeklyMeal[] }>('/menu/upload-ocr', 'POST', body) },
  saveWeeklyMenu: (schedule: WeeklyMeal[]) => adminRequest<{ schedule: WeeklyMeal[] }>('/menu/weekly', 'POST', { schedule }),
  async weeklyMenu(): Promise<unknown> {
    const response = await fetch(apiUrl('/api/menu/weekly'), { cache: 'no-store', credentials: usesAdminCookieSession ? 'include' : 'omit', signal: AbortSignal.timeout(20000) })
    const body = await response.json().catch(() => null)
    if (!response.ok || !body) throw new Error(typeof body?.detail === 'string' ? body.detail : 'Cannot load the weekly menu.')
    return body
  },
}
