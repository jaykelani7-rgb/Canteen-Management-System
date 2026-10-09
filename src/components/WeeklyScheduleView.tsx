import React, { useEffect, useState } from 'react'
import { adminOperationsApi, type WeeklyMeal } from '../lib/adminOperationsApi'

interface WeeklyScheduleViewProps {
  onShowToast?: (title: string, description?: string, type?: 'success' | 'info' | 'warning' | 'error') => void
  onNavigateToUpload?: () => void
}

type DaySchedule = { breakfast: string[]; lunch: string[]; snacks: string[]; dinner: string[] }
const emptyDay = (): DaySchedule => ({ breakfast: [], lunch: [], snacks: [], dinner: [] })

export default function WeeklyScheduleView({
  onNavigateToUpload,
}: WeeklyScheduleViewProps) {
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
      if (active) setSchedule(next)
    }).catch(cause => { if (active) setError((cause as Error).message) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])
  const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
  const currentSchedule = schedule[selectedDay] || emptyDay()

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      {/* Header Info */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h3 className="text-xl font-bold text-[#1D1A16] tracking-tight">
            Weekly Mess & Canteen Timetable
          </h3>
          <p className="text-xs text-stone-500 mt-1">
            Current active rotating menu stored in PostgreSQL database.
          </p>
        </div>

        <button
          onClick={onNavigateToUpload}
          className="px-5 py-2.5 rounded-full bg-[#F25C2C] hover:bg-[#d84e20] text-white text-xs font-bold transition-all shadow-md shadow-[#F25C2C]/25 active:scale-95 cursor-pointer flex items-center gap-2"
        >
          <svg
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"
            />
          </svg>
          <span>Upload New Schedule via OCR</span>
        </button>
      </div>

      {loading && <p role="status" className="text-sm text-stone-500">Loading weekly menu…</p>}
      {error && <p role="alert" className="rounded-2xl border border-red-200 bg-white p-4 text-sm text-red-700">{error}</p>}
      {!loading && !error && !schedule[selectedDay] && <p className="text-sm text-stone-500">No menu has been saved for {selectedDay}.</p>}
      {/* Day Selector Pills */}
      <div className="flex items-center gap-2 overflow-x-auto pb-2 no-scrollbar">
        {days.map((day) => {
          const isSelected = selectedDay === day
          return (
            <button
              key={day}
              onClick={() => setSelectedDay(day)}
              className={`px-5 py-2.5 rounded-full text-xs font-bold transition-all whitespace-nowrap cursor-pointer ${
                isSelected
                  ? 'bg-[#F25C2C] text-white shadow-md shadow-[#F25C2C]/20'
                  : 'bg-white text-stone-700 hover:bg-stone-50 border border-[#E5DFD7]'
              }`}
            >
              {day}
            </button>
          )
        })}
      </div>

      {/* 4 Meal Cards for Selected Day */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Breakfast */}
        <div className="p-7 rounded-3xl bg-white border border-[#E5DFD7] shadow-sm flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-[#E5DFD7]">
              <div className="flex items-center gap-2.5">
                <span className="text-2xl">🍳</span>
                <h4 className="text-base font-bold text-[#1D1A16]">Breakfast</h4>
              </div>
              <span className="text-xs font-mono font-semibold px-3 py-1 rounded-full bg-amber-50 text-amber-900 border border-amber-200">
                07:30 - 10:30
              </span>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {currentSchedule.breakfast.map((dish, i) => (
                <span
                  key={i}
                  className="px-3.5 py-1.5 rounded-full bg-[#FAF7F3] border border-[#E5DFD7] text-xs font-semibold text-[#1D1A16]"
                >
                  {dish}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Lunch */}
        <div className="p-7 rounded-3xl bg-white border border-[#E5DFD7] shadow-sm flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-[#E5DFD7]">
              <div className="flex items-center gap-2.5">
                <span className="text-2xl">🍱</span>
                <h4 className="text-base font-bold text-[#1D1A16]">Lunch</h4>
              </div>
              <span className="text-xs font-mono font-semibold px-3 py-1 rounded-full bg-amber-50 text-amber-900 border border-amber-200">
                12:00 - 15:00
              </span>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {currentSchedule.lunch.map((dish, i) => (
                <span
                  key={i}
                  className="px-3.5 py-1.5 rounded-full bg-[#FAF7F3] border border-[#E5DFD7] text-xs font-semibold text-[#1D1A16]"
                >
                  {dish}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Snacks */}
        <div className="p-7 rounded-3xl bg-white border border-[#E5DFD7] shadow-sm flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-[#E5DFD7]">
              <div className="flex items-center gap-2.5">
                <span className="text-2xl">☕</span>
                <h4 className="text-base font-bold text-[#1D1A16]">Evening Snacks</h4>
              </div>
              <span className="text-xs font-mono font-semibold px-3 py-1 rounded-full bg-amber-50 text-amber-900 border border-amber-200">
                16:30 - 18:30
              </span>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {currentSchedule.snacks.map((dish, i) => (
                <span
                  key={i}
                  className="px-3.5 py-1.5 rounded-full bg-[#FAF7F3] border border-[#E5DFD7] text-xs font-semibold text-[#1D1A16]"
                >
                  {dish}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Dinner */}
        <div className="p-7 rounded-3xl bg-white border border-[#E5DFD7] shadow-sm flex flex-col justify-between space-y-4">
          <div>
            <div className="flex items-center justify-between pb-3 border-b border-[#E5DFD7]">
              <div className="flex items-center gap-2.5">
                <span className="text-2xl">🍛</span>
                <h4 className="text-base font-bold text-[#1D1A16]">Dinner</h4>
              </div>
              <span className="text-xs font-mono font-semibold px-3 py-1 rounded-full bg-amber-50 text-amber-900 border border-amber-200">
                19:30 - 22:30
              </span>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {currentSchedule.dinner.map((dish, i) => (
                <span
                  key={i}
                  className="px-3.5 py-1.5 rounded-full bg-[#FAF7F3] border border-[#E5DFD7] text-xs font-semibold text-[#1D1A16]"
                >
                  {dish}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
