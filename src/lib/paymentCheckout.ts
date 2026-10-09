import { apiClient } from './apiClient'
import type { GatewayCheckout, StudentOrder, WalletTopup } from './studentTypes'
type PaymentResponse = { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string }
interface CheckoutInstance { open(): void; on(event: 'payment.failed', handler: (data: { error?: { description?: string } }) => void): void }
type CheckoutConstructor = new (options: Record<string, unknown>) => CheckoutInstance
declare global { interface Window { Razorpay?: CheckoutConstructor } }
let loader: Promise<CheckoutConstructor> | null = null
export class CheckoutDismissed extends Error {
  constructor(message = 'Payment was not completed. You can resume the pending payment.') { super(message); this.name = 'CheckoutDismissed' }
}
function loadCheckout(): Promise<CheckoutConstructor> {
  if (window.Razorpay) return Promise.resolve(window.Razorpay)
  if (loader) return loader
  loader = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://checkout.razorpay.com/v1/checkout.js'; script.async = true
    const timer = setTimeout(() => { script.remove(); loader = null; reject(new Error('The secure payment window could not load. Check your connection and retry the pending order.')) }, 20000)
    script.onload = () => { clearTimeout(timer); if (window.Razorpay) resolve(window.Razorpay); else { loader = null; reject(new Error('The payment window is unavailable.')) } }
    script.onerror = () => { clearTimeout(timer); script.remove(); loader = null; reject(new Error('The secure payment window could not load. Retry your pending order.')) }
    document.head.appendChild(script)
  })
  return loader
}
async function gatewayCheckout<T>(checkout: GatewayCheckout, description: string, verify: (response: PaymentResponse) => Promise<T>): Promise<T> {
  const Razorpay = await loadCheckout()
  return new Promise<T>((resolve, reject) => {
    let verifying = false, settled = false, failure = ''
    const finish = (cause?: Error, verified?: T) => {
      if (settled) return
      settled = true
      if (cause) reject(cause); else resolve(verified!)
    }
    const instance = new Razorpay({
      key: checkout.keyId, amount: checkout.amountPaise, currency: checkout.currency, order_id: checkout.providerOrderId,
      name: 'Smart Canteen', description, theme: { color: '#F25C2C' },
      handler: async (response: PaymentResponse) => {
        if (verifying || settled) return
        verifying = true
        try { finish(undefined, await verify(response)) } catch (cause) { finish(cause as Error) }
      },
      modal: { ondismiss: () => { if (!verifying) finish(new CheckoutDismissed(failure || undefined)) }, confirm_close: true },
    })
    instance.on('payment.failed', response => { failure = response.error?.description || 'Payment was not completed. You can resume the pending payment.' })
    try { instance.open() } catch (cause) { finish(cause as Error) }
  })
}
export async function completeGatewayPayment(order: StudentOrder): Promise<StudentOrder> {
  if (order.payment === 'Paid') return order
  if (!order.checkout || order.status !== 'Payment Pending') throw new Error('This order cannot start online payment.')
  return gatewayCheckout(order.checkout, 'Order ' + order.number, response => apiClient.verifyPayment(order.orderId, response))
}
export async function completeWalletTopup(topup: WalletTopup): Promise<WalletTopup> {
  if (topup.state === 'captured') return topup
  if (!topup.checkout) throw new Error('This top-up is awaiting payment setup. Refresh its status before retrying.')
  return gatewayCheckout(topup.checkout, 'Canteen wallet top-up', response => apiClient.verifyWalletTopup(topup.id, response))
}
const TOPUP_INTENTS_KEY = 'sco_student_wallet_topup_intents'
export function walletTopupIntent(amount: number): string {
  const paise = Math.round(amount * 100)
  if (!Number.isFinite(amount) || amount <= 0 || Math.abs(amount * 100 - paise) > 0.0001) throw new Error('Enter a positive amount with at most two decimal places.')
  try {
    const saved = JSON.parse(sessionStorage.getItem(TOPUP_INTENTS_KEY) || '{}') as Record<string, string>
    const fingerprint = 'INR:' + paise
    if (typeof saved[fingerprint] === 'string' && saved[fingerprint]) return saved[fingerprint]
    const bytes = crypto.getRandomValues(new Uint8Array(16))
    const key = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
    saved[fingerprint] = key
    sessionStorage.setItem(TOPUP_INTENTS_KEY, JSON.stringify(saved))
    return key
  } catch { throw new Error('Allow session storage before adding funds so retries cannot create duplicate payments.') }
}
export function clearWalletTopupIntent(amount: number) {
  try {
    const saved = JSON.parse(sessionStorage.getItem(TOPUP_INTENTS_KEY) || '{}') as Record<string, string>
    delete saved['INR:' + Math.round(amount * 100)]
    if (Object.keys(saved).length) sessionStorage.setItem(TOPUP_INTENTS_KEY, JSON.stringify(saved))
    else sessionStorage.removeItem(TOPUP_INTENTS_KEY)
  } catch { /* Only anonymous amount fingerprints and retry keys are stored. */ }
}
const INTENT_KEY = 'sco_student_checkout_intent'
export function checkoutIntent(items: { id: string; qty: number }[], paymentMethod: string): string {
  const fingerprint = JSON.stringify({ items: [...items].sort((a, b) => a.id.localeCompare(b.id)), paymentMethod })
  try {
    const saved = JSON.parse(sessionStorage.getItem(INTENT_KEY) || 'null') as { key?: string; fingerprint?: string } | null
    if (saved?.key && saved.fingerprint === fingerprint) return saved.key
    const bytes = crypto.getRandomValues(new Uint8Array(16))
    const key = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')
    sessionStorage.setItem(INTENT_KEY, JSON.stringify({ key, fingerprint }))
    return key
  } catch { throw new Error('Allow session storage before placing an order so retries cannot create duplicate charges.') }
}
export function clearCheckoutIntent() { try { sessionStorage.removeItem(INTENT_KEY) } catch { /* No sensitive identity data is stored. */ } }
