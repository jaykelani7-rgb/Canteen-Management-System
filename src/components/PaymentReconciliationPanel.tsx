import { useEffect, useRef, useState } from 'react'
import { adminOperationsApi, type PaymentReconciliation } from '../lib/adminOperationsApi'
interface Props { onChanged: () => void; onShowToast?: (title: string, description?: string, type?: 'success' | 'info' | 'warning' | 'error') => void }
const stateLabel = (state: string) => state.replace(/_/g, ' ')
const stateStyle = (state: string) => ['failed', 'refund_required', 'reconciliation_required'].includes(state)
  ? 'bg-red-50 border-red-200 text-red-800' : state === 'processed' || state === 'refunded'
    ? 'bg-emerald-50 border-emerald-200 text-emerald-800' : 'bg-amber-50 border-amber-200 text-amber-900'
export default function PaymentReconciliationPanel({ onChanged, onShowToast }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [rows, setRows] = useState<PaymentReconciliation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState<number | null>(null)
  const [providerIds, setProviderIds] = useState<Record<number, string>>({})
  const [refundTarget, setRefundTarget] = useState<PaymentReconciliation | null>(null)
  const [reason, setReason] = useState('')
  const locked = useRef(false), revision = useRef(0), alive = useRef(true)
  const reload = useRef<() => Promise<void>>(async () => {})
  useEffect(() => {
    let active = true, inFlight = false
    alive.current = true
    const load = async () => {
      if (inFlight || locked.current) return
      inFlight = true
      const requestedRevision = revision.current
      try {
        const next = await adminOperationsApi.reconciliation()
        if (active && requestedRevision === revision.current) { setRows(next); setError('') }
      } catch (cause) { if (active) setError((cause as Error).message) }
      finally { inFlight = false; if (active) setLoading(false) }
    }
    reload.current = load
    void load()
    const timer = expanded ? setInterval(() => { if (document.visibilityState === 'visible') void load() }, 15000) : null
    return () => { active = false; alive.current = false; if (timer) clearInterval(timer) }
  }, [expanded])
  const mutate = async (row: PaymentReconciliation, action: () => Promise<unknown>, success: string) => {
    if (locked.current) return
    locked.current = true; revision.current++; setBusyId(row.paymentIntentId); setError('')
    try {
      await action()
      if (!alive.current) return
      setRefundTarget(null); setReason('')
      onShowToast?.(success, 'The backend checked the provider. Current status will be refreshed.', 'success')
      onChanged()
    } catch (cause) {
      if (alive.current) { setError((cause as Error).message); onShowToast?.('Payment action failed', (cause as Error).message, 'error') }
    } finally { locked.current = false; if (alive.current) { setBusyId(null); void reload.current() } }
  }
  const amount = (row: PaymentReconciliation) => (row.amountPaise / 100).toLocaleString('en-IN', { style: 'currency', currency: row.currency })
  const canRefund = (row: PaymentReconciliation) => row.state === 'refund_required' || row.refundStatus === 'failed' || row.refundStatus === 'reconciliation_required'
  const frozenAccounts = rows.filter(row => row.unrecoveredRefundPaise > 0)
  return <section className="rounded-3xl bg-white border border-[#E5DFD7] p-6 shadow-sm">
    <button className="flex w-full items-center justify-between gap-4 text-left" aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>
      <div><h4 className="text-base font-bold text-[#1D1A16]">Payment Review</h4><p className="mt-1 text-xs text-stone-500">Pending payment checks and refunds{!loading && !error ? ' · ' + rows.length + ' to review' : ''}</p></div>
      <span className="text-[#F25C2C] text-lg">{expanded ? '−' : '+'}</span>
    </button>
    {expanded && <div className="mt-5 space-y-4">
      <div className="flex items-center justify-between gap-4"><p className="text-xs text-stone-500">Review an existing payment. Reconciliation does not create another charge.</p><button disabled={busyId !== null} onClick={() => { void reload.current() }} className="text-xs font-bold text-[#F25C2C]">Refresh</button></div>
      {loading && <p role="status" className="text-sm text-stone-500">Loading payments…</p>}
      {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {!loading && !error && !rows.length && <p className="text-sm text-stone-500">No payments require review.</p>}
      {!!frozenAccounts.length && <p role="alert" className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800"><strong>Frozen wallet account{frozenAccounts.length === 1 ? '' : 's'}:</strong> a provider refund exceeded the recoverable wallet balance. Review the unrecovered amounts below and arrange an authorized account adjustment. Rechecking the provider does not clear this debt.</p>}
      {!!rows.length && <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr className="border-b border-[#E5DFD7] text-stone-500"><th className="py-3 pr-4">Payment</th><th className="py-3 pr-4">Amount</th><th className="py-3 pr-4">Status</th><th className="py-3">Action</th></tr></thead><tbody>{rows.map(row => <tr key={row.paymentIntentId} className="border-b border-[#E5DFD7] last:border-0">
        <td className="py-4 pr-4"><p className="font-bold text-[#1D1A16]">{row.purpose === 'wallet_topup' ? 'Wallet top-up' : 'Order #' + row.orderId}</p><p className="mt-1 font-mono text-stone-500">Intent #{row.paymentIntentId} · {row.receipt}</p>{row.providerPaymentId && <p className="mt-1 font-mono text-stone-500">{row.providerPaymentId}</p>}{row.refundId && <p className="mt-1 font-mono text-stone-500">Refund {row.refundId}</p>}</td>
        <td className="py-4 pr-4 font-mono font-bold whitespace-nowrap">{amount(row)}</td>
        <td className="py-4 pr-4"><span className={'inline-block rounded-full border px-2.5 py-1 whitespace-nowrap ' + stateStyle(row.state)}>{stateLabel(row.state)}</span>
          {row.refundStatus && <p className="mt-2"><span className={'inline-block rounded-full border px-2.5 py-1 whitespace-nowrap ' + stateStyle(row.refundStatus)}>Refund: {stateLabel(row.refundStatus)}</span></p>}
          {row.state === 'refund_required' && <p className="mt-2 text-red-700">Payment captured but not credited. Refund required.</p>}
          {row.refundStatus === 'failed' && <p className="mt-2 text-red-700">Refund failed. Review the provider response before retrying.</p>}
          {(row.refundStatus === 'pending' || row.refundStatus === 'created') && <p className="mt-2 text-stone-500">Refund awaiting provider confirmation.</p>}
          {row.unrecoveredRefundPaise > 0 && <p role="alert" className="mt-2 font-bold text-red-700">Account frozen · Unrecovered: {(row.unrecoveredRefundPaise / 100).toLocaleString('en-IN', { style: 'currency', currency: row.currency })}</p>}
        </td>
        <td className="py-4"><div className="flex flex-col items-start gap-2">{row.providerOrderId ? <p className="font-mono text-stone-500">{row.providerOrderId}</p> : <label className="text-stone-500">Existing gateway order ID<input value={providerIds[row.paymentIntentId] || ''} onChange={event => setProviderIds(prev => ({ ...prev, [row.paymentIntentId]: event.target.value }))} disabled={busyId !== null} placeholder="order_…" className="mt-1 block rounded-xl border border-[#E5DFD7] bg-[#FAF7F3] p-2 font-mono text-[#1D1A16]" /></label>}
          <div className="flex flex-wrap gap-2"><button disabled={busyId !== null || (!row.providerOrderId && !providerIds[row.paymentIntentId]?.trim())} onClick={() => { void mutate(row, () => adminOperationsApi.reconcileIntent(row.paymentIntentId, row.providerOrderId || providerIds[row.paymentIntentId]?.trim()), 'Payment check completed') }} className="rounded-full bg-[#F25C2C] px-3 py-2 font-bold text-white disabled:opacity-40">{busyId === row.paymentIntentId ? 'Checking…' : 'Check provider'}</button>
          {canRefund(row) && <button disabled={busyId !== null} onClick={() => { setRefundTarget(row); setReason(''); setError('') }} className="rounded-full border border-[#E5DFD7] bg-[#FAF7F3] px-3 py-2 font-bold text-stone-700">Review refund</button>}</div>
        </div></td>
      </tr>)}</tbody></table></div>}
    </div>}
    {refundTarget && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-5" role="dialog" aria-modal="true" aria-labelledby="refund-title"><div className="w-full max-w-md rounded-3xl border border-[#E5DFD7] bg-white p-6 shadow-xl">
      <h4 id="refund-title" className="text-lg font-bold text-[#1D1A16]">Review refund</h4><p className="mt-2 text-sm text-stone-500">{amount(refundTarget)} · {refundTarget.purpose === 'wallet_topup' ? 'Uncredited wallet top-up' : 'Order #' + refundTarget.orderId}</p><p className="mt-1 text-xs font-mono text-stone-500">{refundTarget.receipt}</p>
      <p className="mt-4 text-xs text-stone-500">The backend validates eligibility and asks the provider to refund this payment. Completion is shown after provider confirmation.</p>
      <label className="mt-4 block text-xs font-bold text-stone-700">Reason<textarea required maxLength={255} value={reason} onChange={event => setReason(event.target.value)} disabled={busyId !== null} className="mt-1 min-h-20 w-full rounded-xl border border-[#E5DFD7] bg-[#FAF7F3] p-3 text-sm font-normal" /></label>
      {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
      <div className="mt-5 flex justify-end gap-3"><button disabled={busyId !== null} onClick={() => setRefundTarget(null)} className="rounded-full bg-stone-100 px-4 py-2 text-xs font-bold text-stone-700">Cancel</button><button disabled={busyId !== null || !reason.trim()} onClick={() => { const target = refundTarget; void mutate(target, () => target.purpose === 'order' && target.orderId !== null ? adminOperationsApi.refundOrder(target.orderId, reason.trim()) : adminOperationsApi.refundIntent(target.paymentIntentId, reason.trim()), 'Refund request checked') }} className="rounded-full bg-[#F25C2C] px-4 py-2 text-xs font-bold text-white disabled:opacity-40">{busyId !== null ? 'Processing…' : 'Request refund'}</button></div>
    </div></div>}
  </section>
}
