import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { formatMoney, type Page, type WalletOut } from '../api/types'
import { Pager } from '../components/Pager'
import { WalletStatusBadge } from '../components/Badge'
import { useAuth } from '../auth/useAuth'

export default function WalletsPage() {
  const [page, setPage] = useState(1)
  const [userId, setUserId] = useState('')
  const [status, setStatus] = useState('')
  const [currency, setCurrency] = useState('')
  const { user: me } = useAuth()
  const queryClient = useQueryClient()

  const { data, isLoading, error } = useQuery({
    queryKey: ['wallets', page, userId, status, currency],
    queryFn: async () =>
      (
        await api.get<Page<WalletOut>>('/wallets/search', {
          params: {
            page,
            size: 20,
            user_id: userId || undefined,
            status: status || undefined,
            currency: currency || undefined,
          },
        })
      ).data,
  })

  const setFrozen = useMutation({
    mutationFn: async (w: WalletOut) => api.post(`/wallets/${w.id}/${w.status === 'frozen' ? 'unfreeze' : 'freeze'}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['wallets'] }),
  })

  return (
    <div>
      <h1>Wallets</h1>
      <div className="filter-bar">
        <input
          placeholder="Filter by user ID"
          value={userId}
          onChange={(e) => {
            setPage(1)
            setUserId(e.target.value)
          }}
        />
        <select
          value={status}
          onChange={(e) => {
            setPage(1)
            setStatus(e.target.value)
          }}
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="frozen">Frozen</option>
          <option value="closed">Closed</option>
        </select>
        <select
          value={currency}
          onChange={(e) => {
            setPage(1)
            setCurrency(e.target.value)
          }}
        >
          <option value="">All currencies</option>
          <option value="ILS">ILS</option>
          <option value="USD">USD</option>
          <option value="EUR">EUR</option>
        </select>
      </div>

      {isLoading && <p>Loading…</p>}
      {error && <p className="error-text">Failed to load wallets.</p>}
      {data && (
        <>
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>User ID</th>
                <th>Currency</th>
                <th>Status</th>
                <th>Balance</th>
                <th>Available</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((w) => (
                <tr key={w.id}>
                  <td>{w.id}</td>
                  <td>{w.user_id}</td>
                  <td>{w.currency}</td>
                  <td>
                    <WalletStatusBadge status={w.status} />
                  </td>
                  <td className="num">{formatMoney(w.balance)}</td>
                  <td className="num">{formatMoney(w.available_balance)}</td>
                  <td>
                    {w.status !== 'closed' && (
                      <button className="btn-secondary" disabled={me?.role !== 'admin' || setFrozen.isPending} onClick={() => setFrozen.mutate(w)}>
                        {w.status === 'frozen' ? 'Unfreeze' : 'Freeze'}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {data.items.length === 0 && (
                <tr>
                  <td colSpan={7} className="muted">
                    No wallets match these filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <Pager page={data.page} pages={data.pages} onChange={setPage} />
        </>
      )}
    </div>
  )
}
