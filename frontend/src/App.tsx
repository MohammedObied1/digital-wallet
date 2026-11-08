import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from './auth/AuthContext'
import Layout from './components/Layout'
import LoginPage from './pages/LoginPage'
import OverviewPage from './pages/OverviewPage'
import UsersPage from './pages/UsersPage'
import WalletsPage from './pages/WalletsPage'
import TransactionsPage from './pages/TransactionsPage'
import FraudPage from './pages/FraudPage'
import AuditPage from './pages/AuditPage'

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<Layout />}>
            <Route path="/" element={<OverviewPage />} />
            <Route path="/users" element={<UsersPage />} />
            <Route path="/wallets" element={<WalletsPage />} />
            <Route path="/transactions" element={<TransactionsPage />} />
            <Route path="/fraud" element={<FraudPage />} />
            <Route path="/audit" element={<AuditPage />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
