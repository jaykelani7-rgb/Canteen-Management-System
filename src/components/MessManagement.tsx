import React, { useEffect, useRef, useState } from 'react'
import { messApi as apiClient } from '../lib/messApi'
import { MessApiError, MessPlan, MessSubscription } from '../lib/messApi'
import type { MessSection } from './AdminSidebar'
import AddMessMemberModal from './AddMessMemberModal'
import MessMembersView from './MessMembersView'
import MessMemberDetails from './MessMemberDetails'
import DailyAttendanceView from './DailyAttendanceView'
import MessPlansView from './MessPlansView'
import { secondaryClass, ToastFn } from './messUi'

export default function MessManagement({ section, onShowToast }: { section: MessSection; onShowToast: ToastFn }) {
  const [members, setMembers] = useState<MessSubscription[]>([])
  const [plans, setPlans] = useState<MessPlan[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [detail, setDetail] = useState<number | null>(null)
  const [modal, setModal] = useState<MessSubscription | 'new' | null>(null)
  const [attendanceRevision, setAttendanceRevision] = useState(0)
  const requestId = useRef(0)

  function failed(e: unknown) {
    // The application gate owns invalid sessions and unmounts protected content.
    if (e instanceof MessApiError && (e.status === 401 || e.status === 403)) return
    const message = e instanceof Error ? e.message : 'Request failed'
    setError(message)
    onShowToast('Mess request failed', message, 'error')
  }

  async function load() {
    const id = ++requestId.current
    setLoading(true)
    setError('')
    try {
      const [list, defaults] = await Promise.all([apiClient.getMessSubscriptions(), apiClient.getMessPlans()])
      if (id === requestId.current) { setMembers(list); setPlans(defaults) }
    } catch (e) {
      if (id === requestId.current) failed(e)
    } finally {
      if (id === requestId.current) setLoading(false)
    }
  }

  useEffect(() => { void load(); return () => { requestId.current++ } }, [])
  useEffect(() => { setError(''); setModal(null); setDetail(null) }, [section])

  return <div className="space-y-5">
    {error && <div role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">{error}<button className={`${secondaryClass} ml-3`} onClick={load}>Retry</button></div>}
    {loading && <p className="text-sm text-stone-500">Refreshing mess data…</p>}
    {section === 'members' && <MessMembersView members={members} plans={plans} add={() => setModal('new')} view={setDetail} edit={setModal} refresh={load} />}
    {section === 'attendance' && <DailyAttendanceView plans={plans} revision={attendanceRevision} view={setDetail} toast={onShowToast} onError={failed} onChanged={load} />}
    {section === 'plans' && <MessPlansView plans={plans} refresh={load} toast={onShowToast} onError={failed} />}
    {modal && plans.length > 0 && <AddMessMemberModal plans={plans} member={modal === 'new' ? undefined : modal} close={() => setModal(null)} onError={failed} saved={() => { setModal(null); onShowToast('Membership saved', 'Subscription and token balance saved.', 'success'); void load() }} />}
    {detail !== null && <MessMemberDetails id={detail} plans={plans} close={() => setDetail(null)} onError={failed} toast={onShowToast} onChanged={() => { setAttendanceRevision(r => r + 1); void load() }} />}
  </div>
}
