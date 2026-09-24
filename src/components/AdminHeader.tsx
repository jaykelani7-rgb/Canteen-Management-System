import React, { useState, useEffect } from 'react'

interface AdminHeaderProps {
  title: string
  subtitle: string
  onQuickAction?: () => void
  actionLabel?: string
  appMode?: 'admin' | 'mobile-preview'
  onToggleMode?: () => void
}

export default function AdminHeader({
  title,
  subtitle,
  onQuickAction,
  actionLabel = '+ Quick Action',
  appMode = 'admin',
  onToggleMode,
}: AdminHeaderProps) {
  const [timeStr, setTimeStr] = useState('')
  const [dayStr, setDayStr] = useState('')

  useEffect(() => {
    const updateTime = () => {
      const now = new Date()
      setTimeStr(
        now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      )
      setDayStr(
        now.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' })
      )
    }
    updateTime()
    const timer = setInterval(updateTime, 1000)
    return () => clearInterval(timer)
  }, [])

  return (
    <header className="px-8 py-5 border-b border-[#E5DFD7] bg-[#F5F0EB]/90 backdrop-blur-md sticky top-0 z-30 flex items-center justify-between gap-6">
      {/* View Title */}
      <div>
        <h2 className="text-2xl font-bold text-[#1D1A16] tracking-tight">
          {title}
        </h2>
        <p className="text-xs font-medium text-stone-500 mt-0.5">
          {subtitle}
        </p>
      </div>

      {/* Right controls: Time, Search, Quick Actions */}
      <div className="flex items-center gap-4">
        {/* Live Day & Clock Badge */}
        <div className="hidden lg:flex items-center gap-2.5 px-4 py-2 rounded-full bg-white border border-[#E5DFD7] shadow-sm">
          <svg
            className="w-4 h-4 text-[#F25C2C]"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <div className="text-xs">
            <span className="font-bold text-[#1D1A16]">{dayStr}</span>
            <span className="mx-1.5 text-stone-300">|</span>
            <span className="font-mono font-medium text-stone-600">{timeStr}</span>
          </div>
        </div>

        {/* Canteen Service Window Pill */}
        <div className="hidden md:flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-amber-50 border border-amber-200/80 text-amber-900 text-xs font-semibold">
          <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse"></span>
          <span>Active Window: Lunch (12:00 - 15:00)</span>
        </div>

        {/* App Switcher Mode Toggle (if student app preview is enabled) */}
        {onToggleMode && (
          <button
            onClick={onToggleMode}
            className="px-3.5 py-2 rounded-full bg-white hover:bg-stone-100 text-stone-700 border border-[#E5DFD7] text-xs font-semibold flex items-center gap-2 transition-all cursor-pointer shadow-sm"
          >
            <span>📱</span>
            <span>{appMode === 'admin' ? 'View Student App' : 'Back to Admin'}</span>
          </button>
        )}

        {/* Primary Action Button */}
        {onQuickAction && (
          <button
            onClick={onQuickAction}
            className="px-5 py-2.5 rounded-full bg-[#F25C2C] hover:bg-[#d84e20] text-white text-xs font-bold transition-all shadow-md shadow-[#F25C2C]/25 active:scale-95 cursor-pointer flex items-center gap-2"
          >
            <span>{actionLabel}</span>
          </button>
        )}
      </div>
    </header>
  )
}
