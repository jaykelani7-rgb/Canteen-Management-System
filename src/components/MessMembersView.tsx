import React, { useState } from 'react'
import { MessPlan, MessSubscription } from '../lib/messApi'
import { dateLabel, inputClass, Kpis, panelClass, primaryClass, secondaryClass, StatusPill, today, TokenBalance } from './messUi'
export default function MessMembersView({ members, plans, add, view, edit, refresh }: {
  members: MessSubscription[]; plans: MessPlan[]; add: () => void; view: (id: number) => void; edit: (s: MessSubscription) => void; refresh: () => void;
}) {
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const [plan, setPlan] = useState('')
  const filtered = members.filter(s => `${s.student_name} ${s.roll_number} ${s.mobile_number}`.toLowerCase().includes(search.trim().toLowerCase()) && (!status || s.status === status) && (!plan || s.plan_type === plan))
  const active = members.filter(s => s.status === 'Active' && s.start_date <= today()).length
  return <div className="space-y-5"><div className="flex flex-wrap items-center justify-between gap-3"><h3 className="text-lg font-bold">Mess Members</h3><button className={primaryClass} disabled={!plans.some(p => p.is_active)} onClick={add}>+ Add Mess Member</button></div>
    <Kpis items={[["Total Members", members.length], ["Active", active], ["Expired", members.filter(s => s.status === 'Expired').length], ["Exhausted", members.filter(s => s.status === 'Exhausted').length]]} />
    <div className={panelClass}><div className="mb-4 flex flex-wrap gap-3"><input aria-label="Search mess members" className={`${inputClass} max-w-md`} placeholder="Search name, roll number or mobile…" value={search} onChange={e => setSearch(e.target.value)} />
      <select aria-label="Filter members by status" className={`${inputClass} sm:w-auto`} value={status} onChange={e => setStatus(e.target.value)}><option value="">All Statuses</option>{['Active', 'Expired', 'Exhausted', 'Cancelled'].map(value => <option key={value}>{value}</option>)}</select>
      <select aria-label="Filter members by plan" className={`${inputClass} sm:w-auto`} value={plan} onChange={e => setPlan(e.target.value)}><option value="">All Plans</option>{plans.map(value => <option key={value.id} value={value.id}>{value.name}</option>)}</select>
      <button className={secondaryClass} onClick={refresh}>Refresh</button></div>
      <div className="overflow-x-auto"><table className="w-full text-left text-xs"><thead className="bg-[#FAF7F3] uppercase text-stone-500"><tr>{['Student', 'Roll No', 'Year', 'Mobile', 'Plan', 'Amount Paid', 'Total Tokens', 'Remaining', 'Start Date', 'End Date', 'Status', 'Actions'].map(h => <th className="whitespace-nowrap p-3" key={h}>{h}</th>)}</tr></thead><tbody>{filtered.map(s => <tr key={s.id} className="border-t border-[#E5DFD7] hover:bg-[#FAF7F3]/60"><td className="p-3"><button className="whitespace-nowrap font-bold hover:text-[#F25C2C]" onClick={() => view(s.id)}>{s.student_name}</button></td><td className="p-3 font-mono">{s.roll_number}</td><td className="whitespace-nowrap p-3">{s.year}</td><td className="p-3">{s.mobile_number}</td><td className="whitespace-nowrap p-3">{plans.find(plan => plan.id === s.plan_type)?.name || s.plan_type}</td><td className="p-3">₹{s.amount_paid}</td><td className="p-3">{s.total_tokens}</td><td className="p-3"><TokenBalance value={s.remaining_tokens} /></td><td className="whitespace-nowrap p-3">{dateLabel(s.start_date)}</td><td className="whitespace-nowrap p-3">{dateLabel(s.end_date)}</td><td className="p-3"><StatusPill status={s.status} /></td><td className="p-3"><div className="flex gap-2"><button className={secondaryClass} onClick={() => view(s.id)}>View</button><button className={secondaryClass} onClick={() => edit(s)}>Edit</button></div></td></tr>)}</tbody></table>{!filtered.length && <p className="p-8 text-center text-sm text-stone-500">No mess members found. Add a paid subscription to begin.</p>}</div>
    </div></div>
}
