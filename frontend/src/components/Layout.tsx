import { NavLink, Outlet, Navigate } from 'react-router-dom'
import { useAuth } from '../auth/useAuth'

const NAV = [
  { to: '/', label: 'Overview', end: true },
  { to: '/users', label: 'Users' },
  { to: '/wallets', label: 'Wallets' },
  { to: '/transactions', label: 'Transactions' },
  { to: '/fraud', label: 'Fraud' },
  { to: '/audit', label: 'Audit Log' },
]

export default function Layout() {
  const { user, loading, logout } = useAuth()

  if (loading) return <div className="page-loading">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  if (user.role !== 'admin' && user.role !== 'support') {
    return (
      <div className="page-loading">
        <p>This dashboard is for support and admin staff only.</p>
        <button onClick={logout}>Sign out</button>
      </div>
    )
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">Wallet Admin</div>
        <nav>
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <div className="whoami">
            <strong>{user.username}</strong>
            <span className={`role-badge role-${user.role}`}>{user.role}</span>
          </div>
          <button className="btn-secondary" onClick={logout}>
            Sign out
          </button>
        </div>
      </aside>
      <main className="content">
        <Outlet />
      </main>
    </div>
  )
}
