import React, { useState } from 'react'
import AdminSidebar, { NavTab } from './AdminSidebar'
import AdminHeader from './AdminHeader'
import OcrMenuUpload from './OcrMenuUpload'
import AlaCarteManagement from './AlaCarteManagement'
import WeeklyScheduleView from './WeeklyScheduleView'
import LiveOrdersView from './LiveOrdersView'
import AnalyticsView from './AnalyticsView'
import Toast, { ToastMessage } from './Toast'

interface AdminDashboardProps {
  appMode?: 'admin' | 'mobile-preview'
  onToggleMode?: () => void
}

export default function AdminDashboard({
  appMode = 'admin',
  onToggleMode,
}: AdminDashboardProps) {
  const [activeTab, setActiveTab] = useState<NavTab>('ocr-upload')
  const [toasts, setToasts] = useState<ToastMessage[]>([
    {
      id: 'welcome-1',
      title: 'Smart Canteen OS Connected',
      description: 'PostgreSQL async pool & Redis caching node active.',
      type: 'success',
    },
  ])

  const showToast = (
    title: string,
    description?: string,
    type: 'success' | 'info' | 'warning' | 'error' = 'info'
  ) => {
    const newToast: ToastMessage = {
      id: `toast-${Date.now()}-${Math.random()}`,
      title,
      description,
      type,
    }
    setToasts((prev) => [...prev, newToast])
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== newToast.id))
    }, 4500)
  }

  const dismissToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }

  const getTabTitle = (tab: NavTab) => {
    switch (tab) {
      case 'ocr-upload':
        return {
          title: 'Menu Upload & OCR Extraction',
          subtitle: 'Upload physical mess timetable charts to digitize weekly meals',
        }
      case 'ala-carte':
        return {
          title: 'A La Carte Inventory & Timing',
          subtitle: 'Manage permanent dishes, unit prices, timing windows, and live availability',
        }
      case 'weekly-schedule':
        return {
          title: 'Active Weekly Schedule',
          subtitle: 'Current rotating mess menu schedule for Breakfast, Lunch, Snacks & Dinner',
        }
      case 'live-orders':
        return {
          title: 'Live Kitchen Orders',
          subtitle: 'Real-time order pipeline and student token preparation queue',
        }
      case 'analytics':
        return {
          title: 'Canteen Sales & Footfall Analytics',
          subtitle: 'Real-time statistics, popular items, and Redis cache hit ratios',
        }
      case 'settings':
        return {
          title: 'Canteen Configuration',
          subtitle: 'Kitchen timing windows, meal service cutoffs, and notification parameters',
        }
    }
  }

  const { title, subtitle } = getTabTitle(activeTab)

  return (
    <div className="flex h-screen bg-[#F5F0EB] text-[#1D1A16] font-sans antialiased overflow-hidden selection:bg-[#F25C2C]/20 selection:text-[#F25C2C]">
      {/* Left Sidebar Navigation */}
      <AdminSidebar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        pendingOrdersCount={4}
        isLiveService={true}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 h-full overflow-hidden">
        {/* Sticky Header */}
        <AdminHeader
          title={title}
          subtitle={subtitle}
          appMode={appMode}
          onToggleMode={onToggleMode}
          onQuickAction={
            activeTab === 'ocr-upload'
              ? () => showToast('OCR Ready', 'Drop an image to start character extraction.', 'info')
              : undefined
          }
          actionLabel={activeTab === 'ocr-upload' ? 'Upload Guide' : '+ Quick Action'}
        />

        {/* Scrollable View Container */}
        <main className="flex-1 overflow-y-auto p-8 no-scrollbar">
          {activeTab === 'ocr-upload' && (
            <OcrMenuUpload
              onShowToast={showToast}
              onScheduleSaved={() => {
                showToast(
                  'PostgreSQL Synchronized',
                  'Weekly menu updated across all 7 days with Redis cache invalidation.',
                  'success'
                )
              }}
            />
          )}

          {activeTab === 'ala-carte' && (
            <AlaCarteManagement onShowToast={showToast} />
          )}

          {activeTab === 'weekly-schedule' && (
            <WeeklyScheduleView
              onShowToast={showToast}
              onNavigateToUpload={() => setActiveTab('ocr-upload')}
            />
          )}

          {activeTab === 'live-orders' && (
            <LiveOrdersView onShowToast={showToast} />
          )}

          {activeTab === 'analytics' && <AnalyticsView />}

          {activeTab === 'settings' && (
            <div className="max-w-4xl mx-auto p-8 rounded-3xl bg-white border border-[#E5DFD7] shadow-sm space-y-6">
              <h4 className="text-lg font-bold text-[#1D1A16]">Canteen Operating Windows</h4>
              <p className="text-xs text-stone-500">
                Configure automated meal evaluation schedules used by <code>GET /api/menu/today</code>.
              </p>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="p-4 rounded-2xl bg-[#FAF7F3] border border-[#E5DFD7]">
                  <p className="text-xs font-bold text-[#1D1A16]">🍳 Breakfast Window</p>
                  <p className="text-xs font-mono text-stone-600 mt-1">07:30 to 10:30 (Cutoff 10:30)</p>
                </div>
                <div className="p-4 rounded-2xl bg-[#FAF7F3] border border-[#E5DFD7]">
                  <p className="text-xs font-bold text-[#1D1A16]">🍱 Lunch Window</p>
                  <p className="text-xs font-mono text-stone-600 mt-1">12:00 to 15:00 (Cutoff 15:00)</p>
                </div>
                <div className="p-4 rounded-2xl bg-[#FAF7F3] border border-[#E5DFD7]">
                  <p className="text-xs font-bold text-[#1D1A16]">☕ Evening Snacks</p>
                  <p className="text-xs font-mono text-stone-600 mt-1">16:30 to 18:30 (Cutoff 18:30)</p>
                </div>
                <div className="p-4 rounded-2xl bg-[#FAF7F3] border border-[#E5DFD7]">
                  <p className="text-xs font-bold text-[#1D1A16]">🍛 Dinner Window</p>
                  <p className="text-xs font-mono text-stone-600 mt-1">19:30 to 22:30 (Cutoff 22:30)</p>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Floating Toast Notification Stack */}
      <Toast toasts={toasts} onDismiss={dismissToast} />
    </div>
  )
}
