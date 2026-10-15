import React, { useState } from 'react'
import { adminOperationsApi, type WeeklyMeal } from '../lib/adminOperationsApi'

interface AdminLunchConfigurationProps {
  day: string
  meal?: WeeklyMeal
  onSaved: (meal: WeeklyMeal) => void
  onShowToast?: (title: string, description?: string, type?: 'success' | 'info' | 'warning' | 'error') => void
}

export function lunchConfigurationError(items: string[], sabjis: string[], enabled: boolean): string {
  if (!enabled) return ''
  if (!items.length) return 'Add the complete lunch contents before enabling lunch orders.'
  if (sabjis.length !== 2 || sabjis.some(value => !value.trim()) || new Set(sabjis.map(value => value.trim().toLocaleLowerCase('en-IN'))).size !== 2) return 'Choose exactly two different sabjis.'
  if (sabjis.some(value => !items.includes(value))) return 'Both sabji options must be included in the complete lunch contents.'
  return ''
}

export default function AdminLunchConfiguration({ day, meal, onSaved, onShowToast }: AdminLunchConfigurationProps) {
  const [contents, setContents] = useState((meal?.items || []).join('\n'))
  const [firstSabji, setFirstSabji] = useState(meal?.sabji_options?.[0] || '')
  const [secondSabji, setSecondSabji] = useState(meal?.sabji_options?.[1] || '')
  const [enabled, setEnabled] = useState(meal?.ordering_enabled === true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const items = [...new Set(contents.split('\n').map(value => value.trim()).filter(Boolean))]

  async function save() {
    if (saving) return
    const sabjis = [firstSabji, secondSabji].filter(Boolean)
    const validation = lunchConfigurationError(items, sabjis, enabled)
    if (validation) { setError(validation); return }
    const payload: WeeklyMeal = { day, meal_type: 'lunch', items, sabji_options: sabjis, ordering_enabled: enabled }
    setSaving(true); setError('')
    try {
      const result = await adminOperationsApi.saveWeeklyMenu([payload])
      const saved = result.schedule?.find(row => row.day === day && row.meal_type === 'lunch') || payload
      onSaved(saved)
      onShowToast?.('Lunch configuration saved', day + ' lunch menu and ordering options are saved.', 'success')
    } catch (cause) {
      const message = (cause as Error).message || 'Cannot save lunch configuration. Please retry.'
      setError(message)
      onShowToast?.('Lunch configuration not saved', message, 'error')
    } finally { setSaving(false) }
  }

  const selectClass = 'mt-2 w-full rounded-xl border border-[#E5DFD7] bg-[#FAF7F3] p-3 text-sm font-normal text-[#1D1A16] disabled:opacity-60'
  return <section aria-label="Lunch menu" className="rounded-3xl border border-[#E5DFD7] bg-white p-7 shadow-sm">
    <div className="flex items-center justify-between gap-3 border-b border-[#E5DFD7] pb-4">
      <div className="flex items-center gap-3"><span aria-hidden="true" className="text-3xl">🍱</span><h4 className="text-lg font-bold text-[#1D1A16]">Lunch</h4></div>
      <span className="shrink-0 rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-mono font-semibold text-amber-900">12:00 – 15:00</span>
    </div>
    <p className="mt-4 text-xs leading-relaxed text-stone-500">Configure {day}'s complete meal. Students can order this day's lunch from 12:00–15:00 IST. Chapati Bhaji is ₹45 (3 chapatis, salad and one chosen sabji); Thali is ₹80 and includes every item below.</p>
    <label className="mt-5 block text-xs font-bold text-stone-700">Complete lunch contents · one item per line
      <textarea aria-label="Complete lunch contents" disabled={saving} value={contents} onChange={event => setContents(event.target.value)} rows={6} className={selectClass} placeholder="Enter all dishes being served" />
    </label>
    <div className="mt-4 grid gap-4 sm:grid-cols-2">
      {[{ value: firstSabji, setter: setFirstSabji, label: 'Sabji option 1' }, { value: secondSabji, setter: setSecondSabji, label: 'Sabji option 2' }].map(({ value, setter, label }) => <label key={label} className="text-xs font-bold text-stone-700">{label}
        <select aria-label={label} value={value} onChange={event => setter(event.target.value)} disabled={saving} className={selectClass}>
          <option value="">Choose from the lunch contents</option>
          {(value && !items.includes(value)) ? <option value={value} disabled>{value} (removed from contents)</option> : null}
          {items.map(item => <option key={item} value={item}>{item}</option>)}
        </select>
      </label>)}
    </div>
    <label className="mt-5 flex items-start gap-3 text-sm font-semibold text-stone-700"><input type="checkbox" checked={enabled} disabled={saving} onChange={event => setEnabled(event.target.checked)} className="mt-0.5 h-4 w-4 accent-[#F25C2C]" /><span>Enable Student lunch ordering<span className="mt-1 block text-xs font-normal text-stone-500">Two different sabjis must be included in the meal. Saved orders keep their original contents if you change this configuration later.</span></span></label>
    {error && <p role="alert" className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}
    <button type="button" disabled={saving} onClick={() => void save()} className="mt-5 rounded-full bg-[#F25C2C] px-5 py-2.5 text-xs font-bold text-white shadow-md shadow-[#F25C2C]/20 hover:bg-[#d84e20] disabled:opacity-50">{saving ? 'Saving lunch…' : 'Save lunch configuration'}</button>
  </section>
}
