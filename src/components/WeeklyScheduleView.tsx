import React, { useEffect, useState } from 'react'
import { adminOperationsApi, type WeeklyMeal } from '../lib/adminOperationsApi'
import AdminLunchConfiguration from './AdminLunchConfiguration'

interface WeeklyScheduleViewProps {
  onShowToast?: (title: string, description?: string, type?: 'success' | 'info' | 'warning' | 'error') => void
  onNavigateToUpload?: () => void
}

type DaySchedule = { breakfast: string[]; lunch: string[]; snacks: string[]; dinner: string[] }
const emptyDay = (): DaySchedule => ({ breakfast: [], lunch: [], snacks: [], dinner: [] })

function MealCard({ title, icon, time, dishes, emptyMessage }: {
  title: string
  icon: string
  time: string
  dishes: string[]
  emptyMessage: string
}) {
  return (
    <section aria-label={title + ' menu'} className="min-h-64 rounded-3xl border border-[#E5DFD7] bg-white p-7 shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b border-[#E5DFD7] pb-4">
        <div className="flex items-center gap-3">
          <span aria-hidden="true" className="text-3xl">{icon}</span>
          <h4 className="text-lg font-bold text-[#1D1A16]">{title}</h4>
        </div>
        <span className="shrink-0 rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-mono font-semibold text-amber-900">
          {time}
        </span>
      </div>

      {dishes.length ? (
        <ul className="mt-5 flex flex-wrap gap-2.5">
          {dishes.map((dish, index) => (
            <li key={title + '-' + index} className="rounded-xl border border-[#E5DFD7] bg-[#FAF7F3] px-4 py-2.5 text-sm font-semibold text-[#1D1A16]">
              {dish}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-5 rounded-2xl border border-dashed border-[#E5DFD7] bg-[#FAF7F3] px-4 py-6 text-sm text-stone-500">
          {emptyMessage}
        </p>
      )}
    </section>
  )
}

export default function WeeklyScheduleView({
  onNavigateToUpload, onShowToast,
}: WeeklyScheduleViewProps) {
  const [weeklyMeals, setWeeklyMeals] = useState<WeeklyMeal[]>([])
  const [schedule, setSchedule] = useState<Record<string, DaySchedule>>({})
  const [selectedDay, setSelectedDay] = useState<string>(new Date().toLocaleDateString('en-US', { timeZone: 'Asia/Kolkata', weekday: 'long' }))
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    adminOperationsApi.weeklyMenu().then(body => {
      const rows = Array.isArray(body) ? body as WeeklyMeal[] : (body as { schedule?: WeeklyMeal[] }).schedule || []
      const next: Record<string, DaySchedule> = {}
      for (const meal of rows) {
        if (!['breakfast', 'lunch', 'snacks', 'dinner'].includes(meal.meal_type) || !Array.isArray(meal.items)) continue
        next[meal.day] ||= emptyDay()
        next[meal.day][meal.meal_type] = meal.items
      }
      if (active) { setSchedule(next); setWeeklyMeals(rows) }
    }).catch(cause => {
      if (active) setError((cause as Error).message)
    }).finally(() => {
      if (active) setLoading(false)
    })
    return () => { active = false }
  }, [])

  const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
  const currentSchedule = schedule[selectedDay] || emptyDay()

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
        <div>
          <h3 className="text-xl font-bold tracking-tight text-[#1D1A16]">
            Weekly Mess &amp; Canteen Timetable
          </h3>
          <p className="mt-1 text-xs text-stone-500">
            Lunch and dinner menus for the selected day, synced with PostgreSQL.
          </p>
        </div>
        <button
          type="button"
          onClick={onNavigateToUpload}
          className="flex cursor-pointer items-center gap-2 rounded-full bg-[#F25C2C] px-5 py-2.5 text-xs font-bold text-white shadow-md shadow-[#F25C2C]/25 transition-all hover:bg-[#d84e20] active:scale-95"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
          </svg>
          <span>Upload New Schedule via OCR</span>
        </button>
      </div>

      {loading && <p role="status" className="text-sm text-stone-500">Loading weekly menu…</p>}
      {error && <p role="alert" className="rounded-2xl border border-red-200 bg-white p-4 text-sm text-red-700">{error}</p>}

      <div aria-label="Choose day" className="flex items-center gap-2 overflow-x-auto pb-2 no-scrollbar">
        {days.map(day => {
          const isSelected = selectedDay === day
          return (
            <button
              key={day}
              type="button"
              onClick={() => setSelectedDay(day)}
              aria-pressed={isSelected}
              className={`cursor-pointer whitespace-nowrap rounded-full px-5 py-2.5 text-xs font-bold transition-all ${
                isSelected
                  ? 'bg-[#F25C2C] text-white shadow-md shadow-[#F25C2C]/20'
                  : 'border border-[#E5DFD7] bg-white text-stone-700 hover:bg-stone-50'
              }`}
            >
              {day}
            </button>
          )
        })}
      </div>

      {!loading && !error && !schedule[selectedDay] && (
        <p className="rounded-2xl border border-dashed border-[#E5DFD7] bg-white p-4 text-sm text-stone-500">
          No menu has been saved for {selectedDay} yet. The lunch and dinner cards will show their menu once it is added.
        </p>
      )}

      <div className="grid grid-cols-1 items-stretch gap-6 md:grid-cols-2">
        {!loading && !error && (['lunch', 'dinner'] as const).map(mealType => <AdminLunchConfiguration
          key={selectedDay + '-' + mealType}
          day={selectedDay}
          mealType={mealType}
          meal={weeklyMeals.find(meal => meal.day === selectedDay && meal.meal_type === mealType)}
          onShowToast={onShowToast}
          onSaved={meal => {
            setWeeklyMeals(previous => [...previous.filter(row => row.day !== meal.day || row.meal_type !== mealType), meal])
            setSchedule(previous => ({ ...previous, [meal.day]: { ...(previous[meal.day] || emptyDay()), [mealType]: meal.items } }))
          }}
        />)}
      </div>
    </div>
  )
}
