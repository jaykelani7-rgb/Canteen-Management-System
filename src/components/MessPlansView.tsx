import React, { useState } from 'react'
import { messApi as apiClient } from '../lib/messApi'
import { MessPlan } from '../lib/messApi'
import { inputClass, panelClass, primaryClass, StatusPill, ToastFn } from './messUi'
function PlanCard({ plan, refresh, toast, onError }: { plan: MessPlan; refresh: () => void; toast: ToastFn; onError: (error: unknown) => void }) {
  const [values, setValues] = useState(plan)
  const [saving, setSaving] = useState(false)
  return <form className={`${panelClass} space-y-4`} onSubmit={async e => { e.preventDefault(); if (saving) return; setSaving(true); try { const { id, ...body } = values; await apiClient.updateMessPlan(id, body); toast('Plan saved', 'Defaults apply to new memberships.', 'success'); refresh() } catch (e) { onError(e) } finally { setSaving(false) } }}>
    <div className="flex items-center justify-between"><h4 className="font-bold">{plan.name}</h4><StatusPill status={values.is_active ? 'Active' : 'Inactive'} /></div>
    <label className="block text-xs font-semibold">Plan Name<input required minLength={2} maxLength={60} className={inputClass} value={values.name} onChange={e => setValues(v => ({ ...v, name: e.target.value }))} /></label>
    {([['amount', 'Amount (₹)', 0, 99999999.99], ['tokens', 'Tokens', 1, 10000], ['duration_days', 'Duration (days)', 1, 366]] as const).map(([key, label, min, max]) => <label className="block text-xs font-semibold" key={key}>{label}<input required type="number" min={min} max={max} step={key === 'amount' ? '0.01' : '1'} className={inputClass} value={values[key]} onChange={e => setValues(v => ({ ...v, [key]: Number(e.target.value) }))} /></label>)}
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={values.is_active} onChange={e => setValues(v => ({ ...v, is_active: e.target.checked }))} />Active for new subscriptions</label>
    <button className={primaryClass} disabled={saving}>{saving ? 'Saving…' : 'Save Plan'}</button>
  </form>
}
export default function MessPlansView(props: { plans: MessPlan[]; refresh: () => void; toast: ToastFn; onError: (error: unknown) => void }) {
  return <div className="space-y-4"><h3 className="text-lg font-bold">Plans / Settings</h3><p className="text-sm text-stone-500">Changes affect new memberships. Existing paid subscriptions retain their agreed tokens and dates.</p><div className="grid gap-5 lg:grid-cols-2">{props.plans.map(plan => <PlanCard key={JSON.stringify(plan)} plan={plan} {...props} />)}</div></div>
}
