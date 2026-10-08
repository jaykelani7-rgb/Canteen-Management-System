import AdminAuthGate from './components/AdminAuthGate'
import AdminDashboard from './components/AdminDashboard'

export default function App() {
  return (
    <AdminAuthGate>
      {({ admin, onSignOut }) => <AdminDashboard admin={admin} onSignOut={onSignOut} />}
    </AdminAuthGate>
  )
}
