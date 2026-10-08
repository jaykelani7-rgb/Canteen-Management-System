import React, { useEffect, useState } from 'react'
import { messApi as apiClient } from '../lib/messApi'
import { Attendance, MessDetail, MessPlan } from '../lib/messApi'
import { dateLabel, inputClass, Kpis, Modal, panelClass, primaryClass, secondaryClass, StatusPill, timeLabel, today, ToastFn } from './messUi'
export default function MessMemberDetails({ id, plans, close, onError, toast, onChanged }: { id: number; plans: MessPlan[]; close: () => void; onError: (error: unknown) => void; toast: ToastFn; onChanged: () => void }) {
  const [detail, setDetail] = useState<MessDetail | null>(null)
  const [error, setError] = useState('')
  const [undo, setUndo] = useState<Attendance | null>(null)
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  async function reverse(event: React.FormEvent) {
    event.preventDefault()
    if (!undo || saving || reason.trim().length < 3) return
    setSaving(true); setError('')
    try {
      const result = await apiClient.undoMealAttendance(undo.id, reason.trim())
      setDetail(await apiClient.getMessSubscription(id)); setUndo(null); setReason('')
      toast('Attendance reversed', `${result.attendance.reversal_token_before} → ${result.subscription.remaining_tokens} tokens`, 'success'); onChanged()
    } catch (cause) { onError(cause); setError(cause instanceof Error ? cause.message : 'Could not reverse attendance') }
    finally { setSaving(false) }
  }
  useEffect(() => { let current = true; apiClient.getMessSubscription(id).then(d => { if (current) setDetail(d) }).catch(e => { if (current) { setError(e.message); onError(e) } }); return () => { current = false } }, [id])
  return <Modal title="Student Mess Details" close={close}>{error ? <p role="alert" className="text-rose-700">{error}</p> : !detail ? <p>Loading history…</p> : <div className="space-y-5">
    <div className={panelClass}><h4 className="text-lg font-bold">{detail.student_name}</h4><p className="text-sm text-stone-500">{detail.roll_number} · {detail.year} · {detail.branch} · {detail.mobile_number}</p><div className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4"><p>Plan<br /><strong>{plans.find(plan => plan.id === detail.plan_type)?.name || detail.plan_type}</strong></p><p>Amount Paid<br /><strong>₹{detail.amount_paid}</strong></p><p>Total Tokens<br /><strong>{detail.total_tokens}</strong></p><p>Status<br /><StatusPill status={detail.status} /></p><p>Start<br />{dateLabel(detail.start_date)}</p><p>End<br />{dateLabel(detail.end_date)}</p><p>Payment<br />{detail.payment_method}</p><p>Receipt<br />{detail.payment_reference || '—'}</p></div>{detail.notes && <p className="mt-3 text-sm">{detail.notes}</p>}</div>
    <Kpis items={[["Tokens Used", detail.tokens_used], ["Tokens Remaining", detail.remaining_tokens], ["Meals Taken", detail.meals_taken]]} />
    <h4 className="font-bold">Attendance History</h4><div className="overflow-x-auto rounded-2xl border border-[#E5DFD7]"><table className="w-full text-left text-xs"><thead className="bg-[#FAF7F3] text-stone-500"><tr>{['Date', 'Meal', 'Status', 'Token Before', 'Token After', 'Marked At (IST)', 'Marked By', 'Reversal Audit', 'Action'].map(h => <th className="whitespace-nowrap p-3" key={h}>{h}</th>)}</tr></thead><tbody>{detail.attendance.map(a => <tr key={a.id} className="border-t border-[#E5DFD7]"><td className="whitespace-nowrap p-3">{dateLabel(a.meal_date)}</td><td className="p-3">{a.meal_type}</td><td className="p-3"><StatusPill status={a.status} /></td><td className="p-3">{a.token_before}</td><td className="p-3">{a.token_after}</td><td className="whitespace-nowrap p-3">{timeLabel(a.marked_at)}</td><td className="p-3">{a.marked_by || 'Demo seed'}</td><td className="min-w-40 p-3">{a.undo_reason ? <>{a.undo_reason}<br />{a.reversal_token_before} → {a.reversal_token_after}<br />{a.reversed_at && timeLabel(a.reversed_at)} · Admin #{a.reversed_by_admin_id}</> : '—'}</td><td className="p-3">{a.status === 'Taken' && a.meal_date === today() && <button className={secondaryClass} disabled={saving} onClick={() => { setUndo(a); setReason('') }}>Undo</button>}</td></tr>)}</tbody></table>{!detail.attendance.length && <p className="p-5 text-sm text-stone-500">No meals marked yet.</p>}</div>
  <div>{undo && <form onSubmit={reverse} className="space-y-3 rounded-2xl border border-[#E5DFD7] bg-[#FAF7F3] p-4"><p className="font-semibold">Undo {undo.meal_type}</p><label className="block text-sm">Reason<textarea className={inputClass} required minLength={3} maxLength={500} value={reason} onChange={e => setReason(e.target.value)} /></label><button className={primaryClass} disabled={saving || reason.trim().length < 3}>{saving ? "Reversing…" : "Confirm Undo"}</button><button type="button" className={`${secondaryClass} ml-2`} disabled={saving} onClick={() => setUndo(null)}>Cancel</button></form>}</div></div>}</Modal>
}
