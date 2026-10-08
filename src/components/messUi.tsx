import React, { useEffect, useRef } from 'react'
export const inputClass = 'w-full rounded-xl border border-[#E5DFD7] bg-[#FAF7F3] px-3 py-2.5 text-sm outline-none focus:border-[#F25C2C] focus:ring-2 focus:ring-[#F25C2C]/15'
export const primaryClass = 'rounded-full bg-[#F25C2C] px-5 py-2.5 text-sm font-bold text-white shadow-sm hover:bg-[#d84e20] disabled:opacity-50 disabled:cursor-not-allowed'
export const secondaryClass = 'rounded-full border border-[#E5DFD7] bg-white px-4 py-2 text-sm font-semibold hover:bg-stone-50 disabled:opacity-50'
export const panelClass = 'rounded-3xl border border-[#E5DFD7] bg-white p-5 shadow-sm'
export type ToastFn = (title: string, description?: string, type?: 'success' | 'info' | 'warning' | 'error') => void
export const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
export const dateLabel = (value: string) => new Date(value + 'T00:00:00').toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
export const timeLabel = (value: string) => new Date(value).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit' })
export function StatusPill({ status }: { status: string }) {
  return <span className={`inline-block whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-bold ${status === 'Active' || status === 'Taken' ? 'bg-green-50 text-green-700' : status === 'Exhausted' || status === 'Cancelled' ? 'bg-rose-50 text-rose-700' : 'bg-amber-50 text-amber-800'}`}>{status}</span>
}
export function TokenBalance({ value }: { value: number }) {
  return <div className="whitespace-nowrap"><strong className="text-lg">{value}</strong>{value <= 5 && <span className={`ml-2 rounded-full px-2 py-1 text-[10px] font-bold ${value === 0 ? 'bg-rose-50 text-rose-700' : 'bg-amber-50 text-amber-800'}`}>{value === 0 ? 'NO TOKENS' : 'LOW TOKENS'}</span>}</div>
}
export function Kpis({ items }: { items: [string, number][] }) {
  return <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">{items.map(([label, count]) => <div className={panelClass} key={label}><p className="text-xs font-bold uppercase tracking-wide text-stone-500">{label}</p><p className="mt-2 text-3xl font-bold">{count}</p></div>)}</div>
}
export function Modal({ title, close, children }: { title: string; close: () => void; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const closeRef = useRef(close)
  closeRef.current = close
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const focusables = () => Array.from(ref.current?.querySelectorAll<HTMLElement>('button:not([disabled]), input, select, textarea, [tabindex="0"]') || [])
    focusables()[0]?.focus()
    const keydown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeRef.current()
      if (e.key === 'Tab') {
        const list = focusables(), first = list[0], last = list[list.length - 1]
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus() }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus() }
      }
    }
    document.addEventListener('keydown', keydown)
    return () => { document.removeEventListener('keydown', keydown); previous?.focus() }
  }, [])
  return <div className="fixed inset-0 z-40 flex items-center justify-center bg-stone-900/40 p-3 sm:p-6"><div ref={ref} role="dialog" aria-modal="true" aria-label={title} className="max-h-[90vh] w-full max-w-4xl overflow-y-auto rounded-3xl border border-[#E5DFD7] bg-white p-5 shadow-xl sm:p-7"><div className="mb-5 flex items-center justify-between gap-3"><h3 className="text-xl font-bold">{title}</h3><button aria-label="Close dialog" onClick={close} className={secondaryClass}>✕</button></div>{children}</div></div>
}
