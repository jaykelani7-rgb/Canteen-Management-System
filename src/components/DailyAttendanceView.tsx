import React, { useEffect, useRef, useState } from 'react'
import { messApi as apiClient } from '../lib/messApi'
import { Attendance, DailyRow, Meal, MessApiError, MessPlan, MessStats } from '../lib/messApi'
import { inputClass, Kpis, Modal, panelClass, primaryClass, secondaryClass, timeLabel, today, TokenBalance, ToastFn } from './messUi'
export default function DailyAttendanceView({ plans, revision: externalRevision, view, toast, onError, onChanged }: {
  plans: MessPlan[]; revision: number; view: (id: number) => void; toast: ToastFn; onError: (error: unknown) => void; onChanged: () => void;
}) {
  const [day, setDay] = useState(today())
  const [meal, setMeal] = useState<Meal>('Lunch')
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('All')
  const [plan, setPlan] = useState('')
  const [rows, setRows] = useState<DailyRow[]>([])
  const [stats, setStats] = useState<MessStats | null>(null)
  const [busy, setBusy] = useState<number[]>([])
  const locks = useRef(new Set<number>())
  const version = useRef(0)
  const selection = useRef('')
  selection.current = `${day}|${meal}|${search}|${filter}|${plan}`
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const [undo, setUndo] = useState<Attendance | null>(null)
  const [reason, setReason] = useState('')
  const refresh = () => setRevision(r => r + 1)
  useEffect(() => {
    const requestVersion = ++version.current
    setLoading(true); setError(''); setRows([]); setStats(null)
    const timer = setTimeout(() => {
      Promise.all([apiClient.getMessAttendance({ meal_date: day, meal_type: meal, search, filter, plan_type: plan }), apiClient.getMessStats({ meal_date: day, meal_type: meal })])
        .then(([list, totals]) => { if (version.current === requestVersion) { setRows(list); setStats(totals) } })
        .catch(e => { if (version.current === requestVersion) { setError(e.message); onError(e) } })
        .finally(() => { if (version.current === requestVersion) setLoading(false) })
    }, search ? 250 : 0)
    return () => { clearTimeout(timer); version.current++ }
  }, [day, meal, search, filter, plan, revision, externalRevision])
  async function mutate(row: DailyRow, reverse?: Attendance) {
    const id = row.subscription.id
    if (locks.current.has(id)) return
    locks.current.add(id); setBusy([...locks.current])
    const currentSelection = selection.current
    try {
      const result = reverse ? await apiClient.undoMealAttendance(reverse.id, reason.trim()) : await apiClient.markMealTaken(id, day, meal)
      if (selection.current === currentSelection) setRows(list => list.map(r => r.subscription.id !== id ? r : {
        ...r, subscription: result.subscription, attendance: reverse ? null : result.attendance,
        can_mark: !!reverse && result.subscription.status === 'Active' && day === today(),
      }))
      if (reverse) { setUndo(null); setReason('') }
      toast(reverse ? 'Attendance reversed' : 'Meal marked', `${result.subscription.student_name}: ${reverse ? result.attendance.reversal_token_before : result.attendance.token_before} → ${result.subscription.remaining_tokens} tokens`, 'success')
      onChanged(); refresh()
    } catch (e) {
      if (e instanceof MessApiError && e.status === 409 && e.message.includes('already marked')) toast('Already Marked', e.message, 'error')
      else onError(e)
      // A conflict/timeout may mean another staff member completed the operation.
      refresh()
    } finally { locks.current.delete(id); setBusy([...locks.current]) }
  }
  return <div className="space-y-5"><h3 className="text-lg font-bold">Daily Mess Attendance</h3>
    <div className={`${panelClass} grid gap-3 sm:grid-cols-2 xl:grid-cols-6`}>
      <label className="text-xs font-semibold">Date<input aria-label="Attendance date" className={inputClass} type="date" value={day} onChange={e => { if (e.target.value) setDay(e.target.value) }} /></label>
      <label className="text-xs font-semibold">Meal<select className={inputClass} value={meal} onChange={e => setMeal(e.target.value as Meal)}>{['Lunch', 'Dinner'].map(m => <option key={m}>{m}</option>)}</select></label>
      <label className="text-xs font-semibold xl:col-span-2">Search<input className={inputClass} placeholder="Name, roll number or mobile" value={search} onChange={e => setSearch(e.target.value)} /></label>
      <label className="text-xs font-semibold">Status<select className={inputClass} value={filter} onChange={e => setFilter(e.target.value)}>{['All', 'Taken', 'Not Taken', 'Low Tokens', 'No Tokens'].map(f => <option key={f}>{f}</option>)}</select></label>
      <label className="text-xs font-semibold">Plan<select className={inputClass} value={plan} onChange={e => setPlan(e.target.value)}><option value="">All Plans</option>{plans.map(value => <option key={value.id} value={value.id}>{value.name}</option>)}</select></label>
      <button className={secondaryClass} disabled={loading} onClick={refresh}>Refresh</button>
    </div>
    {day !== today() && <p className="rounded-xl bg-amber-50 p-3 text-sm text-amber-800">Historical and future dates are read-only. Only today's meals can be marked or undone.</p>}
    {error && <p role="alert" className="rounded-xl bg-rose-50 p-4 text-sm text-rose-700">{error}</p>}
    {stats && <><Kpis items={[["Active Mess Students", stats.eligible_members], ["Already Taken", stats.meals_taken], ["Remaining to Serve", stats.meals_remaining], ["Tokens Consumed Today", stats.tokens_consumed_today]]} /><p className="text-xs text-stone-500">Low tokens: {stats.low_token_members} · No tokens: {stats.zero_token_members} · Expired memberships: {stats.expired_memberships}. Totals cover all members for this date and meal.</p></>}
    <div className={`${panelClass} overflow-x-auto`} aria-busy={loading}>{loading ? <p className="p-4 text-sm text-stone-500">Loading attendance…</p> : <><table className="w-full text-left text-sm"><thead className="bg-[#FAF7F3] text-xs uppercase text-stone-500"><tr>{['Student', 'Roll No', 'Year', 'Plan', 'Remaining Tokens', 'Attendance', 'Action'].map(h => <th className="whitespace-nowrap p-3" key={h}>{h}</th>)}</tr></thead><tbody>{rows.map(row => <tr className="border-t border-[#E5DFD7]" key={row.subscription.id}><td className="whitespace-nowrap p-3 font-bold">{row.subscription.student_name}</td><td className="p-3 font-mono text-xs">{row.subscription.roll_number}</td><td className="whitespace-nowrap p-3">{row.subscription.year}</td><td className="whitespace-nowrap p-3">{plans.find(plan => plan.id === row.subscription.plan_type)?.name || row.subscription.plan_type}</td><td className="p-3"><TokenBalance value={row.subscription.remaining_tokens} /></td><td className="whitespace-nowrap p-3">{row.attendance ? <div><button disabled className="rounded-full bg-green-50 px-4 py-2 font-bold text-green-700">✓ TAKEN</button><p className="mt-1 text-xs text-stone-500">{timeLabel(row.attendance.marked_at)} · {row.attendance.marked_by || 'Demo seed'}</p></div> : <button className={primaryClass} disabled={!row.can_mark || busy.includes(row.subscription.id)} onClick={() => mutate(row)}>{busy.includes(row.subscription.id) ? 'Marking…' : 'FOOD TAKEN'}</button>}</td><td className="p-3"><div className="flex gap-2"><button className={secondaryClass} onClick={() => view(row.subscription.id)}>View</button>{row.attendance && day === today() && <button className={secondaryClass} disabled={busy.includes(row.subscription.id)} onClick={() => { setUndo(row.attendance); setReason('') }}>Undo</button>}</div></td></tr>)}</tbody></table>{!rows.length && !error && <p className="p-8 text-center text-sm text-stone-500">No matching subscriptions for this date.</p>}</>}</div>
    {undo && <Modal title={`Undo ${undo.meal_type}`} close={() => setUndo(null)}><form className="space-y-4" onSubmit={e => { e.preventDefault(); const row = rows.find(r => r.subscription.id === undo.subscription_id); if (row) mutate(row, undo) }}><p className="text-sm text-stone-500">Restore one token and preserve this meal's audit record.</p><label className="block text-sm font-semibold">Reason<textarea required minLength={3} maxLength={500} className={inputClass} value={reason} onChange={e => setReason(e.target.value)} placeholder="Marked wrong student" /></label><button className={primaryClass} disabled={reason.trim().length < 3 || busy.includes(undo.subscription_id)}>{busy.includes(undo.subscription_id) ? 'Reversing…' : 'Confirm Undo'}</button></form></Modal>}
  </div>
}
