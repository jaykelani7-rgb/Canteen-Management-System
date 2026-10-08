import React, { useState } from 'react'
import { messApi as apiClient } from '../lib/messApi'
import { MessInput, MessPlan, MessSubscription } from '../lib/messApi'
import { inputClass, Modal, primaryClass, secondaryClass, today } from './messUi'

function endDate(start: string, days: number) { const d = new Date(start + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + days); return d.toISOString().slice(0, 10) }
export default function AddMessMemberModal({ plans, member, close, saved, onError }: {
  plans: MessPlan[]; member?: MessSubscription; close: () => void; saved: () => void; onError: (error: unknown) => void;
}) {
  const first = plans.find(p => p.is_active) || plans[0]
  const [values, setValues] = useState<MessInput>(member ? {
    student_name: member.student_name, roll_number: member.roll_number, year: member.year, branch: member.branch,
    mobile_number: member.mobile_number, plan_type: member.plan_type, amount_paid: member.amount_paid, total_tokens: member.total_tokens,
    start_date: member.start_date, end_date: member.end_date, payment_method: member.payment_method,
    payment_reference: member.payment_reference, notes: member.notes,
  } : { student_name: '', roll_number: '', year: '2nd Year', branch: '', mobile_number: '', plan_type: first.id,
    amount_paid: Number(first.amount), total_tokens: first.tokens, start_date: today(), end_date: endDate(today(), first.duration_days),
    payment_method: 'Cash', payment_reference: '', notes: '' })
  const [status, setStatus] = useState<'Active' | 'Cancelled'>(member?.status === 'Cancelled' ? 'Cancelled' : 'Active')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  function field(key: keyof MessInput, value: string | number) { setValues(v => ({ ...v, [key]: value })) }
  async function submit(e: React.FormEvent) {
    e.preventDefault(); if (saving) return; setSaving(true); setError('')
    try { if (member) await apiClient.updateMessSubscription(member.id, { ...values, status }); else await apiClient.createMessSubscription(values); saved() }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not save member'); onError(e) }
    finally { setSaving(false) }
  }
  return <Modal title={member ? 'Edit Mess Member' : 'Add Mess Member'} close={close}><form onSubmit={submit} className="space-y-5">
    <div className="grid gap-4 sm:grid-cols-2">
      {([['student_name', 'Student Name'], ['roll_number', 'Roll Number'], ['year', 'Year'], ['branch', 'Branch'], ['mobile_number', 'Mobile Number']] as const).map(([key, label]) => <label key={key} className="space-y-1 text-xs font-semibold">{label}<input className={inputClass} required maxLength={key === 'student_name' || key === 'branch' ? 100 : 30} minLength={key === 'mobile_number' ? 8 : key === 'roll_number' ? 3 : key === 'student_name' ? 2 : 1} value={values[key]} onChange={e => field(key, e.target.value)} /></label>)}
      <label className="space-y-1 text-xs font-semibold">Plan<select className={inputClass} value={values.plan_type} onChange={e => {
        const plan = plans.find(p => p.id === e.target.value)!;
        setValues(v => ({ ...v, plan_type: plan.id, amount_paid: Number(plan.amount), total_tokens: plan.tokens, end_date: endDate(v.start_date, plan.duration_days) }))
      }}>{plans.filter(p => p.is_active || p.id === member?.plan_type).map(p => <option key={p.id} value={p.id}>{p.name} — ₹{p.amount} — {p.tokens} Tokens{!p.is_active ? ' (Inactive)' : ''}</option>)}</select></label>
      <label className="space-y-1 text-xs font-semibold">Amount Paid (₹)<input className={inputClass} type="number" min="0" max="99999999.99" step="0.01" required value={values.amount_paid} onChange={e => field('amount_paid', Number(e.target.value))} /></label>
      <label className="space-y-1 text-xs font-semibold">Total Tokens<input className={inputClass} type="number" min="1" max="10000" required value={values.total_tokens} onChange={e => field('total_tokens', Number(e.target.value))} /></label>
      <label className="space-y-1 text-xs font-semibold">Start Date<input className={inputClass} type="date" required value={values.start_date} onChange={e => {
        const start = e.target.value; if (!start) return; const plan = plans.find(p => p.id === values.plan_type)!;
        setValues(v => ({ ...v, start_date: start, end_date: endDate(start, plan.duration_days) }))
      }} /></label>
      <label className="space-y-1 text-xs font-semibold">End Date<input className={inputClass} type="date" min={values.start_date} required value={values.end_date} onChange={e => field('end_date', e.target.value)} /></label>
      <label className="space-y-1 text-xs font-semibold">Payment Method<select className={inputClass} value={values.payment_method} onChange={e => field('payment_method', e.target.value)}>{['Cash', 'UPI', 'Card', 'Bank Transfer', ...(!['Cash', 'UPI', 'Card', 'Bank Transfer'].includes(values.payment_method) ? [values.payment_method] : [])].map(p => <option key={p}>{p}</option>)}</select></label>
      <label className="space-y-1 text-xs font-semibold">Payment Reference / Receipt (optional)<input className={inputClass} maxLength={100} value={values.payment_reference || ''} onChange={e => field('payment_reference', e.target.value)} /></label>
      {member && <label className="space-y-1 text-xs font-semibold">Membership<select className={inputClass} value={status} onChange={e => setStatus(e.target.value as typeof status)}><option>Active</option><option>Cancelled</option></select></label>}
      <label className="space-y-1 text-xs font-semibold sm:col-span-2">Notes (optional)<textarea className={inputClass} maxLength={2000} value={values.notes || ''} onChange={e => field('notes', e.target.value)} /></label>
    </div><p className="text-xs text-stone-500">Plan values are defaults. Correct them only when necessary. Existing attendance and tokens used are preserved when editing.</p>
    {error && <p role="alert" className="text-sm text-rose-700">{error}</p>}
    <div className="flex justify-end gap-3"><button type="button" className={secondaryClass} disabled={saving} onClick={close}>Cancel</button><button className={primaryClass} disabled={saving}>{saving ? 'Saving…' : member ? 'Save Changes' : 'Add Mess Member'}</button></div>
  </form></Modal>
}
