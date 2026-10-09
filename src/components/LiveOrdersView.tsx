import React, { useEffect, useRef, useState } from 'react'
import { adminOperationsApi, type AdminOrder } from '../lib/adminOperationsApi'
import PaymentReconciliationPanel from './PaymentReconciliationPanel'
import type { StudentOrderStatus } from '../lib/studentTypes'

export interface OrderItem {
  id: string
  orderId: number
  token_number: string
  student_name: string
  roll_no: string
  items: { name: string; qty: number; price: number }[]
  total_amount: number
  status: StudentOrderStatus
  order_time: string
  prep_timer_mins: number
  refund_status: string | null
  cancellation_reason: string | null
}

interface LiveOrdersViewProps {
  onShowToast?: (title: string, description?: string, type?: 'success' | 'info' | 'warning' | 'error') => void
}

function toKitchenOrder(order: AdminOrder): OrderItem {
  return { id: order.id, orderId: order.orderId, token_number: order.pickupToken || order.number,
    student_name: order.studentName, roll_no: order.rollNumber, items: order.items, total_amount: order.total,
    status: order.status, order_time: new Date(order.createdAt || order.date).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit' }),
    prep_timer_mins: order.prepTimeMinutes, refund_status: order.refundStatus || null, cancellation_reason: order.cancellationReason || null }
}
function nextOrderStatus(status: StudentOrderStatus): StudentOrderStatus | null {
  return status === 'Queued' ? 'Preparing' : status === 'Preparing' || status === 'Delayed' ? 'Ready' : status === 'Ready' ? 'Completed' : null
}
export default function LiveOrdersView({ onShowToast }: LiveOrdersViewProps) {
  const [orders, setOrders] = useState<OrderItem[]>([])
  const [selectedStatusTab, setSelectedStatusTab] = useState<string>('All')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<Set<number>>(new Set())
  const [cancelTarget, setCancelTarget] = useState<OrderItem | null>(null)
  const [cancelReason, setCancelReason] = useState('')
  const reloadOrders = useRef<() => Promise<void>>(async () => {})
  const revision = useRef(0)
  const mutations = useRef(new Set<number>())
  useEffect(() => {
    let active = true
    let inFlight = false
    const load = async () => {
      if (inFlight || mutations.current.size) return
      inFlight = true
      const requestedRevision = revision.current
      try {
        const rows = await adminOperationsApi.orders()
        if (active && requestedRevision === revision.current && !mutations.current.size) { setOrders(rows.map(toKitchenOrder)); setError('') }
      } catch (cause) { if (active) setError((cause as Error).message) }
      finally { inFlight = false; if (active) setLoading(false) }
    }
    reloadOrders.current = load
    void load()
    const timer = setInterval(() => { if (document.visibilityState === 'visible') void load() }, 5000)
    return () => { active = false; clearInterval(timer) }
  }, [])
  const handleAdvanceStatus = async (order: OrderItem) => {
    const nextStatus = nextOrderStatus(order.status)
    if (!nextStatus || mutations.current.has(order.orderId)) return
    revision.current++; mutations.current.add(order.orderId); setBusy(new Set(mutations.current))
    try {
      const updated = await adminOperationsApi.setOrderStatus(order.orderId, nextStatus)
      setOrders(prev => prev.map(row => row.orderId === updated.orderId ? toKitchenOrder({ ...updated, studentName: row.student_name, rollNumber: row.roll_no }) : row))
      setError('')
      onShowToast?.('Order ' + order.token_number + ' Updated', 'Status saved as ' + updated.status + '.', 'success')
    } catch (cause) { setError((cause as Error).message); onShowToast?.('Order update failed', (cause as Error).message, 'error') }
    finally { mutations.current.delete(order.orderId); setBusy(new Set(mutations.current)) }
  }

  const cancelOrder = async () => {
    const order = cancelTarget
    if (!order || !cancelReason.trim() || mutations.current.has(order.orderId)) return
    revision.current++; mutations.current.add(order.orderId); setBusy(new Set(mutations.current))
    try {
      const updated = await adminOperationsApi.setOrderStatus(order.orderId, 'Cancelled', cancelReason.trim())
      setOrders(prev => prev.map(row => row.orderId === updated.orderId ? toKitchenOrder({ ...updated, studentName: row.student_name, rollNumber: row.roll_no }) : row))
      setCancelTarget(null); setCancelReason(''); setError('')
      onShowToast?.('Order Cancelled', updated.refundStatus ? 'Refund status: ' + updated.refundStatus.replace(/_/g, ' ') : 'Cancellation saved.', 'success')
    } catch (cause) { setError((cause as Error).message); onShowToast?.('Cancellation failed', (cause as Error).message, 'error') }
    finally { mutations.current.delete(order.orderId); setBusy(new Set(mutations.current)) }
  }

  const filteredOrders = orders.filter((order) => {
    if (selectedStatusTab === 'All') return true
    return order.status === selectedStatusTab
  })

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      {/* Header Info */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-xl font-bold text-[#1D1A16] tracking-tight">
            Live Kitchen Order Queue
          </h3>
          <p className="text-xs text-stone-500 mt-1">
            Real-time student food orders received from student mobile app and digital tokens.
          </p>
        </div>

        {/* Status filters */}
        <div className="flex items-center gap-1.5 p-1 rounded-full bg-white border border-[#E5DFD7] shadow-2xs">
          {['All', 'Payment Pending', 'Queued', 'Preparing', 'Ready', 'Completed', 'Cancelled'].map((tab) => {
            const isSelected = selectedStatusTab === tab
            return (
              <button
                key={tab}
                onClick={() => setSelectedStatusTab(tab)}
                className={`px-3.5 py-1.5 rounded-full text-xs font-bold transition-all cursor-pointer ${
                  isSelected
                    ? 'bg-[#F25C2C] text-white shadow-sm'
                    : 'text-stone-600 hover:text-stone-900'
                }`}
              >
                {tab}
              </button>
            )
          })}
        </div>
      </div>

      {loading && <p role="status" className="text-sm text-stone-500">Loading kitchen orders…</p>}
      {error && <p role="alert" className="rounded-2xl border border-red-200 bg-white p-4 text-sm text-red-700">{error}</p>}
      {!loading && !error && !filteredOrders.length && <p className="rounded-3xl border border-[#E5DFD7] bg-white p-8 text-sm text-stone-500">No orders in this queue.</p>}
      {/* Orders Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredOrders.map((order) => {
          const statusColors: Record<OrderItem['status'], { badge: string; border: string }> = {
            'Payment Pending': { badge: 'bg-amber-50 text-amber-800 border-amber-200', border: 'border-[#E5DFD7]' },
            Queued: { badge: 'bg-stone-100 text-stone-700 border-stone-200', border: 'border-[#E5DFD7]' },
            Preparing: { badge: 'bg-amber-50 text-amber-800 border-amber-200', border: 'border-amber-300' },
            Ready: { badge: 'bg-emerald-50 text-emerald-800 border-emerald-200', border: 'border-emerald-300' },
            Delayed: { badge: 'bg-amber-50 text-amber-800 border-amber-200', border: 'border-amber-300' },
            'Picked Up': { badge: 'bg-stone-100 text-stone-400 border-stone-200', border: 'border-stone-200' },
            Cancelled: { badge: 'bg-red-50 text-red-700 border-red-200', border: 'border-stone-200' },
            Completed: { badge: 'bg-stone-100 text-stone-400 border-stone-200', border: 'border-stone-200' },
          }

          return (
            <div
              key={order.id}
              className={`p-6 rounded-3xl bg-white border ${statusColors[order.status].border} shadow-sm flex flex-col justify-between space-y-6 hover:shadow-md transition-all`}
            >
              <div>
                {/* Token & Status Header */}
                <div className="flex items-center justify-between pb-4 border-b border-[#E5DFD7]">
                  <div className="flex items-center gap-2.5">
                    <span className="text-lg font-mono font-extrabold text-[#F25C2C]">
                      {order.token_number}
                    </span>
                    <span className="text-[11px] font-mono text-stone-500">
                      {order.order_time}
                    </span>
                  </div>
                  <span
                    className={`px-3 py-1 rounded-full text-xs font-bold border ${statusColors[order.status].badge}`}
                  >
                    {order.status}
                  </span>
                </div>

                {/* Student Info */}
                <div className="mt-3">
                  <h5 className="text-sm font-bold text-[#1D1A16]">{order.student_name}</h5>
                  <p className="text-[11px] font-mono text-stone-500">{order.roll_no}</p>
                </div>

                {/* Items List */}
                <div className="mt-4 space-y-2">
                  {order.items.map((item, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between text-xs font-semibold text-stone-800"
                    >
                      <div className="flex items-center gap-2">
                        <span className="w-5 h-5 rounded-md bg-[#FAF7F3] border border-[#E5DFD7] text-[10px] font-bold flex items-center justify-center text-stone-600">
                          {item.qty}x
                        </span>
                        <span className="truncate max-w-[180px]">{item.name}</span>
                      </div>
                      <span className="font-mono text-stone-500">₹{item.price}</span>
                    </div>
                  ))}
                </div>
              </div>

              {order.refund_status && <p role="status" className="text-xs font-semibold text-amber-900">Refund: {order.refund_status.replace(/_/g, ' ')}</p>}
              {order.cancellation_reason && <p className="text-xs text-stone-500">Cancellation: {order.cancellation_reason}</p>}
              {['Queued', 'Preparing', 'Delayed', 'Payment Pending'].includes(order.status) && <button disabled={busy.has(order.orderId)} onClick={() => { setCancelTarget(order); setCancelReason(''); setError('') }} className="self-start text-xs font-bold text-stone-500 hover:text-[#F25C2C]">Cancel order</button>}
              {/* Bottom Total & Action */}
              <div className="pt-4 border-t border-[#E5DFD7] flex items-center justify-between">
                <div>
                  <p className="text-[10px] uppercase font-bold text-stone-600">Total Bill</p>
                  <p className="text-base font-bold text-[#1D1A16]">₹{order.total_amount}</p>
                </div>

                {nextOrderStatus(order.status) ? (
                  <button
                    onClick={() => void handleAdvanceStatus(order)}
                    disabled={busy.has(order.orderId)}
                    className="px-4 py-2 rounded-full bg-[#F25C2C] hover:bg-[#d84e20] text-white text-xs font-bold transition-all shadow-sm active:scale-95 cursor-pointer flex items-center gap-1.5"
                  >
                    <span>
                      {busy.has(order.orderId) ? 'Saving…' : order.status === 'Queued'
                        ? 'Start Cooking →'
                        : (order.status === 'Preparing' || order.status === 'Delayed')
                        ? 'Mark Ready ✓'
                        : 'Complete & Handover'}
                    </span>
                  </button>
                ) : (
                  <span className="text-xs font-bold text-stone-400">{order.status}</span>
                )}
              </div>
            </div>
          )
        })}
      </div>
      <PaymentReconciliationPanel onShowToast={onShowToast} onChanged={() => { revision.current++; void reloadOrders.current() }} />
      {cancelTarget && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-5" role="dialog" aria-modal="true" aria-labelledby="cancel-order-title"><div className="w-full max-w-md rounded-3xl border border-[#E5DFD7] bg-white p-6 shadow-xl">
        <h4 id="cancel-order-title" className="text-lg font-bold text-[#1D1A16]">Cancel order {cancelTarget.token_number}</h4><p className="mt-2 text-sm text-stone-500">{cancelTarget.student_name} · ₹{cancelTarget.total_amount}</p><p className="mt-3 text-xs text-stone-500">The backend validates cancellation and handles any eligible refund. External refunds remain pending until the provider confirms them.</p>
        <label className="mt-4 block text-xs font-bold text-stone-700">Cancellation reason<textarea required maxLength={255} disabled={busy.has(cancelTarget.orderId)} value={cancelReason} onChange={event => setCancelReason(event.target.value)} className="mt-1 min-h-20 w-full rounded-xl border border-[#E5DFD7] bg-[#FAF7F3] p-3 text-sm font-normal" /></label>
        {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
        <div className="mt-5 flex justify-end gap-3"><button disabled={busy.has(cancelTarget.orderId)} onClick={() => setCancelTarget(null)} className="rounded-full bg-stone-100 px-4 py-2 text-xs font-bold text-stone-700">Keep order</button><button disabled={!cancelReason.trim() || busy.has(cancelTarget.orderId)} onClick={() => { void cancelOrder() }} className="rounded-full bg-[#F25C2C] px-4 py-2 text-xs font-bold text-white disabled:opacity-40">{busy.has(cancelTarget.orderId) ? 'Saving…' : 'Confirm cancellation'}</button></div>
      </div></div>}
    </div>
  )
}
