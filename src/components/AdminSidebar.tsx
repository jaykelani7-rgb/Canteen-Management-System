import React, { useState } from 'react'
import type { AdminUser } from '../lib/adminApi'

export type MessSection = 'members' | 'attendance' | 'plans'
const messSections: { id: MessSection; label: string }[] = [
  { id: 'members', label: 'Members' },
  { id: 'attendance', label: 'Daily Attendance' },
  { id: 'plans', label: 'Plans / Settings' },
]
const navOrder: NavTab[] = ['ala-carte', 'weekly-schedule', 'live-orders', 'analytics', 'settings', 'ocr-upload', 'mess-management']

export type NavTab =
  | 'ocr-upload'
  | 'ala-carte'
  | 'weekly-schedule'
  | 'live-orders'
  | 'analytics'
  | 'settings'
  | 'mess-management'

interface SidebarProps {
  admin: AdminUser
  onSignOut: () => void
  messSection: MessSection
  onSelectMessSection: (section: MessSection) => void
  activeTab: NavTab
  onSelectTab: (tab: NavTab) => void
  pendingOrdersCount?: number
  isLiveService?: boolean
}

export default function AdminSidebar({
  admin,
  onSignOut,
  messSection,
  onSelectMessSection,
  activeTab,
  onSelectTab,
  pendingOrdersCount = 6,
  isLiveService = true,
}: SidebarProps) {
  const [messExpanded, setMessExpanded] = useState(false)
  const navItems: {
    id: NavTab
    label: string
    icon: React.ReactNode
    badge?: string | number
  }[] = [
    { id: 'mess-management', label: 'Mess Management', icon: <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"><path strokeLinecap="round" strokeLinejoin="round" d="M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2m20 0v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75M13 7a4 4 0 11-8 0 4 4 0 018 0z" /></svg> },
    {
      id: 'ocr-upload',
      label: 'Menu Upload (OCR)',
      badge: 'AI',
      icon: (
        <svg
          className="w-5 h-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"
          />
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M15 13a3 3 0 11-6 0 3 3 0 016 0z"
          />
        </svg>
      ),
    },
    {
      id: 'ala-carte',
      label: 'A La Carte',
      icon: (
        <svg
          className="w-5 h-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
          />
        </svg>
      ),
    },
    {
      id: 'weekly-schedule',
      label: 'Weekly Schedule',
      icon: (
        <svg
          className="w-5 h-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"
          />
        </svg>
      ),
    },
    {
      id: 'live-orders',
      label: 'Live Orders',
      badge: pendingOrdersCount > 0 ? pendingOrdersCount : undefined,
      icon: (
        <svg
          className="w-5 h-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z"
          />
        </svg>
      ),
    },
    {
      id: 'analytics',
      label: 'Analytics',
      icon: (
        <svg
          className="w-5 h-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
          />
        </svg>
      ),
    },
    {
      id: 'settings',
      label: 'Settings',
      icon: (
        <svg
          className="w-5 h-5"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
          />
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
          />
        </svg>
      ),
    },
  ]

  return (
    <aside className="w-64 shrink-0 flex flex-col justify-between p-5 bg-[#F5F0EB] border-r border-[#E5DFD7] h-screen select-none">
      {/* Top Branding */}
      <div className="min-h-0 flex flex-1 flex-col">
        <div className="flex shrink-0 items-center gap-3 px-3 py-2 mb-6">
          <div className="w-10 h-10 rounded-2xl bg-[#F25C2C] flex items-center justify-center text-white shadow-md shadow-[#F25C2C]/20">
            <svg
              className="w-6 h-6"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth="2.2"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253"
              />
            </svg>
          </div>
          <div>
            <h1 className="font-bold text-[#1D1A16] text-base leading-tight tracking-tight">
              Smart Canteen
            </h1>
            <p className="text-xs font-semibold text-[#F25C2C] tracking-wide uppercase">
              Admin OS
            </p>
          </div>
        </div>

        {/* Live Status indicator card */}
        <div className="shrink-0 mx-1 mb-6 px-3.5 py-2.5 rounded-2xl bg-white border border-[#E5DFD7] shadow-sm flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
            </span>
            <span className="text-xs font-semibold text-[#1D1A16]">
              {isLiveService ? 'Service Online' : 'Kitchen Paused'}
            </span>
          </div>
          <span className="text-[10px] font-mono font-medium px-2 py-0.5 rounded-full bg-stone-100 text-stone-600 border border-stone-200">
            v1.0
          </span>
        </div>

        {/* Navigation List - Pill Shaped Links */}
        <nav aria-label="Admin navigation" className="min-h-0 flex flex-col gap-1.5 overflow-y-auto pb-3 no-scrollbar">
          <p className="px-3 text-[11px] font-bold uppercase tracking-wider text-stone-600 mb-1">
            Menu & Operations
          </p>
          {[...navItems].sort((a, b) => navOrder.indexOf(a.id) - navOrder.indexOf(b.id)).map((item) => {
            const isActive = activeTab === item.id
            return (
              <React.Fragment key={item.id}>
              <button
                aria-current={isActive && item.id !== 'mess-management' ? 'page' : undefined}
                aria-expanded={item.id === 'mess-management' ? messExpanded : undefined}
                aria-controls={item.id === 'mess-management' ? 'mess-navigation' : undefined}
                onClick={() => {
                  if (item.id === 'mess-management') {
                    setMessExpanded(isActive ? !messExpanded : true)
                  }
                  onSelectTab(item.id)
                }}
                className={`w-full flex items-center justify-between px-4 py-3 rounded-full text-sm font-semibold transition-all duration-200 cursor-pointer ${
                  isActive
                    ? 'bg-[#F25C2C] text-white shadow-md shadow-[#F25C2C]/25'
                    : 'text-[#1D1A16] hover:bg-white/80 hover:text-stone-900'
                }`}
              >
                <div className="flex items-center gap-3">
                  <span className={isActive ? 'text-white' : 'text-stone-500'}>
                    {item.icon}
                  </span>
                  <span>{item.label}</span>
                </div>

                {item.id === 'mess-management' && <svg className={`h-4 w-4 shrink-0 transition-transform ${messExpanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="m6 9 6 6 6-6" /></svg>}
                {item.badge !== undefined && (
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-bold transition-colors ${
                      isActive
                        ? 'bg-white/25 text-white'
                        : typeof item.badge === 'number'
                        ? 'bg-[#F25C2C] text-white'
                        : 'bg-stone-200 text-stone-700'
                    }`}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
              {item.id === 'mess-management' && messExpanded && <div id="mess-navigation" className="ml-7 flex flex-col gap-1 border-l border-[#E5DFD7] pl-3">
                {messSections.map(section => <button key={section.id}
                  aria-current={isActive && messSection === section.id ? 'page' : undefined}
                  onClick={() => onSelectMessSection(section.id)}
                  className={`rounded-xl px-3 py-2.5 text-left text-xs font-semibold transition-colors ${isActive && messSection === section.id ? 'bg-white text-[#F25C2C] shadow-sm' : 'text-stone-600 hover:bg-white/80 hover:text-[#1D1A16]'}`}>{section.label}</button>)}
              </div>}
              </React.Fragment>
            )
          })}
        </nav>
      </div>

      {/* Admin User Profile Card at Bottom */}
      <div className="shrink-0 mt-3 p-3.5 rounded-2xl bg-white border border-[#E5DFD7] shadow-sm flex items-center justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <div className="shrink-0 w-9 h-9 rounded-full bg-gradient-to-tr from-stone-800 to-stone-600 text-white font-bold flex items-center justify-center text-xs shadow-inner">
            {admin.username.slice(0, 2).toUpperCase()}
          </div>
          <div className="min-w-0">
            <p className="text-xs font-bold text-[#1D1A16] truncate">
              {admin.username}
            </p>
            <p className="text-[11px] text-stone-500 truncate">
              Administrator
            </p>
          </div>
        </div>
        <button
          onClick={onSignOut}
          title="Sign Out"
          aria-label="Sign Out"
          className="ml-2 h-8 w-8 shrink-0 rounded-full bg-[#F25C2C]/10 text-[#F25C2C] flex items-center justify-center hover:bg-[#F25C2C]/20"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path strokeLinecap="round" strokeLinejoin="round" d="M9 5H5v14h4m6-14 7 7-7 7m7-7H9" /></svg>
        </button>
      </div>
    </aside>
  )
}
