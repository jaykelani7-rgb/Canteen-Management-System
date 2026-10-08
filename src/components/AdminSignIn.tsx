import { useState, type FormEvent } from 'react'

interface Props { onSignIn: (username: string, password: string) => Promise<void>; busy: boolean; error: string; onRetry?: () => Promise<void> }

function CanteenMark() {
  return <svg width="25" height="25" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-3-1-6-1-9 1Z" /><path d="M12 5v15" /></svg>
}

export default function AdminSignIn({ onSignIn, busy, error, onRetry }: Props) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [validation, setValidation] = useState('')
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!username.trim() || !password) { setValidation('Enter your username and password.'); return }
    setValidation('')
    void onSignIn(username.trim(), password)
  }
  const input = 'mt-2 w-full rounded-xl border border-[#E5DFD7] bg-[#FAF7F3] px-4 py-3 text-sm outline-none transition focus:border-[#F25C2C] focus:ring-2 focus:ring-[#F25C2C]/15 disabled:opacity-60'

  return <main className="min-h-screen bg-[#F5F0EB] text-[#1D1A16] font-sans">
    <header className="flex items-center gap-3 border-b border-[#E5DFD7] px-6 py-5 sm:px-10">
      <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#F25C2C] text-white shadow-sm"><CanteenMark /></span>
      <div><p className="font-display text-lg font-bold leading-tight">Smart Canteen</p><p className="mt-0.5 text-xs font-medium tracking-[0.12em] text-[#F25C2C]">ADMIN OS</p></div>
      <span className="ml-auto hidden items-center gap-2 text-xs text-[#7D756D] sm:flex"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><rect x="5" y="10" width="14" height="11" rx="2" /><path d="M8 10V7a4 4 0 0 1 8 0v3" /></svg>Administrator access</span>
    </header>
    <div className="mx-auto grid max-w-6xl items-center gap-10 px-6 py-10 sm:px-10 lg:min-h-[calc(100vh-86px)] lg:grid-cols-2 lg:gap-20 lg:py-14">
      <section className="max-w-lg">
        <p className="mb-4 text-xs font-semibold uppercase tracking-[0.16em] text-[#F25C2C]">Made for the everyday rush</p>
        <h1 className="font-display text-4xl font-bold leading-[1.12] tracking-tight sm:text-5xl">A good meal starts<br />with a great team.</h1>
        <p className="mt-5 max-w-sm text-sm leading-7 text-[#7D756D]">Your menus, members and daily service. Together in one familiar workspace.</p>
        <div aria-hidden="true" className="relative mt-9 hidden max-w-sm rounded-3xl border border-[#E5DFD7] bg-[#EFE7DE] px-7 py-7 sm:block">
          <div className="rounded-2xl border border-[#E5DFD7] bg-white p-5 shadow-sm">
            <div className="flex items-center justify-between"><span className="text-xs font-semibold text-[#7D756D]">THE CANTEEN, CONNECTED</span><span className="h-2 w-2 rounded-full bg-[#F25C2C]" /></div>
            <div className="mt-5 flex items-center gap-4"><span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#FFF0E9] text-[#F25C2C]"><svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M3 19h18M5 16a7 7 0 0 1 14 0H5ZM12 6V4m-2 0h4" /></svg></span><div><p className="font-display text-lg font-bold">Ready for service.</p><p className="mt-1 text-xs text-[#7D756D]">Every member. Every meal.</p></div></div>
            <div className="mt-5 grid grid-cols-3 gap-2 border-t border-[#EEE8E1] pt-4">{['Menus', 'Members', 'Attendance'].map(label => <span key={label} className="rounded-lg bg-[#FAF7F3] py-2 text-center text-[10px] font-medium text-[#7D756D]">{label}</span>)}</div>
          </div>
          <span className="absolute -right-3 -bottom-3 flex h-11 w-11 items-center justify-center rounded-2xl border-4 border-[#F5F0EB] bg-[#F25C2C] text-white"><svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m5 12 4 4L19 6" /></svg></span>
        </div>
      </section>
      <section className="w-full rounded-3xl border border-[#E5DFD7] bg-white p-7 shadow-sm sm:p-9" aria-labelledby="admin-sign-in-title">
        <span className="mb-5 inline-flex h-11 w-11 items-center justify-center rounded-2xl bg-[#FFF0E9] text-[#F25C2C]"><svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m12 3 8 4v5c0 5-8 9-8 9s-8-4-8-9V7l8-4Z" /><path d="m9 12 2 2 4-4" /></svg></span>
        <h2 id="admin-sign-in-title" className="font-display text-2xl font-bold tracking-tight">Admin Sign In</h2>
        <p className="mt-2 text-sm leading-6 text-[#7D756D]">Welcome back. Sign in to open your canteen workspace.</p>
        <form onSubmit={submit} className="mt-7 space-y-5" aria-busy={busy}>
          <label className="block text-sm font-medium" htmlFor="admin-username">Username<input id="admin-username" name="username" autoComplete="username" autoCapitalize="none" spellCheck={false} value={username} onChange={event => setUsername(event.target.value)} disabled={busy} className={input} placeholder="Your admin username" required /></label>
          <div><label className="block text-sm font-medium" htmlFor="admin-password">Password</label><div className="relative"><input id="admin-password" name="password" autoComplete="current-password" type={showPassword ? 'text' : 'password'} value={password} onChange={event => setPassword(event.target.value)} disabled={busy} className={`${input} pr-12`} placeholder="Enter your password" required /><button type="button" onClick={() => setShowPassword(value => !value)} aria-label={showPassword ? 'Hide password' : 'Show password'} aria-pressed={showPassword} className="absolute right-3 top-5 rounded text-[#7D756D] focus-visible:outline-2 focus-visible:outline-[#F25C2C]" disabled={busy}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" />{showPassword && <path d="m3 3 18 18" />}</svg></button></div></div>
          {(validation || error) && <p role="alert" className="rounded-xl border border-[#F2D6CD] bg-[#FFF5F0] px-4 py-3 text-sm leading-6 text-[#AE3F22]">{validation || error}</p>}
          <button type="submit" disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#F25C2C] px-5 py-3.5 text-sm font-semibold text-white shadow-sm transition hover:bg-[#D84E20] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#F25C2C] disabled:cursor-wait disabled:opacity-65">{busy && <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />}{busy ? 'Signing in…' : 'Sign In'}{!busy && <span aria-hidden="true">→</span>}</button>
          {onRetry && <button type="button" onClick={() => void onRetry()} disabled={busy} className="w-full text-sm font-medium text-[#F25C2C] hover:underline">Retry session check</button>}
        </form>
        <p className="mt-6 border-t border-[#EEE8E1] pt-5 text-xs leading-5 text-[#7D756D]">For canteen administrators and authorised staff.</p>
      </section>
    </div>
  </main>
}
