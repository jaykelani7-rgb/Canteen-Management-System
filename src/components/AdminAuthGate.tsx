import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { AdminApiError, adminLogin, adminLogout, getAdminMe, getAdminToken, onAdminSessionEnded, type AdminUser } from '../lib/adminApi'
import AdminSignIn from './AdminSignIn'

interface Props { children: (session: { admin: AdminUser; onSignOut: () => void }) => ReactNode }

export default function AdminAuthGate({ children }: Props) {
  const [admin, setAdmin] = useState<AdminUser | null>(null)
  const [checking, setChecking] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [unavailable, setUnavailable] = useState(false)
  const requestId = useRef(0)
  const signingIn = useRef(false)

  const checkSession = useCallback(async () => {
    const id = ++requestId.current
    if (!getAdminToken()) { setAdmin(null); setChecking(false); return }
    setChecking(true)
    setError('')
    try {
      const current = await getAdminMe()
      if (id === requestId.current) { setAdmin(current); setUnavailable(false) }
    } catch (cause) {
      if (id !== requestId.current) return
      setAdmin(null)
      setError(cause instanceof Error ? cause.message : 'Unable to verify your admin session.')
      setUnavailable(cause instanceof AdminApiError && (cause.status === 0 || cause.status >= 500))
    } finally { if (id === requestId.current) setChecking(false) }
  }, [])

  useEffect(() => {
    const unsubscribe = onAdminSessionEnded((message) => {
      requestId.current++
      setAdmin(null)
      setChecking(false)
      setUnavailable(false)
      setError(message)
    })
    void checkSession()
    const revalidate = () => { if (getAdminToken() && !signingIn.current && document.visibilityState === 'visible') void checkSession() }
    window.addEventListener('focus', revalidate)
    document.addEventListener('visibilitychange', revalidate)
    return () => {
      requestId.current++
      unsubscribe()
      window.removeEventListener('focus', revalidate)
      document.removeEventListener('visibilitychange', revalidate)
    }
  }, [checkSession])

  // Close even an idle dashboard when its signed token expires; the server remains authoritative.
  useEffect(() => {
    if (!admin) return
    let timer: ReturnType<typeof setTimeout> | undefined
    try {
      const payload = getAdminToken()?.split('.')[1]
      if (payload) {
        const expires = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/'))).exp
        if (typeof expires === 'number') timer = setTimeout(() => void checkSession(), Math.max(0, Math.min(expires * 1000 - Date.now(), 2147483647)))
      }
    } catch { void checkSession() }
    return () => { if (timer) clearTimeout(timer) }
  }, [admin, checkSession])

  const signIn = async (username: string, password: string) => {
    if (signingIn.current) return
    signingIn.current = true
    setBusy(true)
    setError('')
    setUnavailable(false)
    const id = ++requestId.current
    try {
      await adminLogin(username, password)
      const current = await getAdminMe()
      if (id !== requestId.current) return
      // Let the confirmation be announced before opening the authenticated workspace.
      setAdmin(current)
    } catch (cause) {
      if (id === requestId.current) {
        setError(cause instanceof Error ? cause.message : 'Sign-in failed. Please try again.')
        setUnavailable(cause instanceof AdminApiError && (cause.status === 0 || cause.status >= 500))
      }
    } finally { signingIn.current = false; setBusy(false) }
  }

  if (checking) return <div className="min-h-screen bg-[#F5F0EB] flex items-center justify-center p-6 text-[#1D1A16] font-sans"><div role="status" className="rounded-3xl border border-[#E5DFD7] bg-white p-8 text-center shadow-sm"><div className="mx-auto mb-4 h-7 w-7 animate-spin rounded-full border-2 border-[#E5DFD7] border-t-[#F25C2C]" /><p className="font-semibold">Opening Smart Canteen</p><p className="mt-2 text-sm text-[#7D756D]">Checking your admin session…</p></div></div>
  if (admin) return <>{children({ admin, onSignOut: adminLogout })}</>
  return <AdminSignIn onSignIn={signIn} busy={busy} error={error} onRetry={unavailable && getAdminToken() ? checkSession : undefined} />
}
