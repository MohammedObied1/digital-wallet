import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { formatMoney, type Page, type TransactionOut } from '../api/types'
import { Pager } from '../components/Pager'
import { TransactionStatusBadge } from '../components/Badge'

export default function TransactionsPage() {
  const [page, setPage] = useState(1)
  const [walletId, setWalletId] = useState('')
  const [status, setStatus] = useState('')
  const [type, setType] = useState('')

  const { data, isLoading, error } = useQuery({
    queryKey: ['transactions', page, walletId, status, type],
    queryFn: async () =>
      (
        await api.get<Page<TransactionOut>>('/transactions', {
          params: {
            page,
            size: 20,
            wallet_id: walletId || undefined,
            status: status || undefined,
            type: type || undefined,
          },
        })
      ).data,
  })

  return (
    <div>
      <h1>Transactions</h1>
      <div className="filter-bar">
        <input
          placeholder="Filter by wallet ID"
          value={walletId}
          onChange={(e) => {
            setPage(1)
            setWalletId(e.target.value)
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
          {['pending', 'processing', 'completed', 'failed', 'reversed', 'refunded'].map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          value={type}
          onChange={(e) => {
            setPage(1)
            setType(e.target.value)
          }}
        >
          <option value="">All types</option>
          {['deposit', 'withdrawal', 'transfer', 'payment_request', 'refund', 'reversal'].map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>

      {isLoading && <p>Loading…</p>}
      {error && <p className="error-text">Failed to load transactions.</p>}
      {data && (
        <>
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Type</th>
                <th>Status</th>
                <th>Sender</th>
                <th>Receiver</th>
                <th>Amount</th>
                <th>Currency</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((t) => (
                <tr key={t.id}>
                  <td>{t.id}</td>
                  <td>{t.type}</td>
                  <td>
                    <TransactionStatusBadge status={t.status} />
                  </td>
                  <td>{t.sender_wallet_id ?? '—'}</td>
                  <td>{t.receiver_wallet_id ?? '—'}</td>
                  <td className="num">{formatMoney(t.amount)}</td>
                  <td>{t.currency}</td>
                  <td>{new Date(t.created_at).toLocaleString()}</td>
                </tr>
              ))}
              {data.items.length === 0 && (
                <tr>
                  <td colSpan={8} className="muted">
                    No transactions match these filters.
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
