import React from 'react'

export interface ToastMessage {
  id: string
  title: string
  description?: string
  type?: 'success' | 'info' | 'warning' | 'error'
}

interface ToastProps {
  toasts: ToastMessage[]
  onDismiss: (id: string) => void
}

export default function Toast({ toasts, onDismiss }: ToastProps) {
  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-3 max-w-sm pointer-events-none">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className="pointer-events-auto flex items-start gap-3 p-4 rounded-2xl bg-[#1D1A16] text-white shadow-xl shadow-stone-900/15 border border-stone-800 animate-[sco-toast-in_0.25s_ease-out] transition-all"
        >
          <div className="mt-0.5">
            {toast.type === 'success' && (
              <span className="flex items-center justify-center w-5 h-5 rounded-full bg-[#F25C2C] text-white text-xs font-bold">
                ✓
              </span>
            )}
            {toast.type === 'error' && (
              <span className="flex items-center justify-center w-5 h-5 rounded-full bg-rose-500 text-white text-xs font-bold">
                ✕
              </span>
            )}
            {toast.type === 'warning' && (
              <span className="flex items-center justify-center w-5 h-5 rounded-full bg-amber-500 text-black text-xs font-bold">
                !
              </span>
            )}
            {(!toast.type || toast.type === 'info') && (
              <span className="flex items-center justify-center w-5 h-5 rounded-full bg-stone-700 text-stone-300 text-xs font-bold">
                i
              </span>
            )}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold tracking-tight text-stone-100">
              {toast.title}
            </p>
            {toast.description && (
              <p className="text-xs text-stone-400 mt-0.5 leading-relaxed">
                {toast.description}
              </p>
            )}
          </div>
          <button
            onClick={() => onDismiss(toast.id)}
            className="text-stone-400 hover:text-white text-xs p-1 rounded-lg transition-colors cursor-pointer"
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  )
}
