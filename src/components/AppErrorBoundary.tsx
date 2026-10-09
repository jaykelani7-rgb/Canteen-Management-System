import { Component, type ReactNode } from 'react'
export default class AppErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    if (!this.state.failed) return this.props.children
    return <div role="alert" className="min-h-dvh bg-[#F5F0EB] flex items-center justify-center p-6 text-[#1D1A16] font-sans"><div className="max-w-md rounded-3xl border border-[#E5DFD7] bg-white p-8 shadow-sm"><p className="text-lg font-bold">Smart Canteen could not open this screen</p><p className="mt-2 text-sm text-stone-500">Reload to restore your session and retrieve your saved orders.</p><button onClick={() => window.location.reload()} className="mt-5 rounded-2xl bg-[#F25C2C] px-5 py-3 font-semibold text-white">Reload app</button></div></div>
  }
}
