import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { AdminStats } from '../api/types'

export default function OverviewPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['admin-stats'],
    queryFn: async () => (await api.get<AdminStats>('/admin/stats')).data,
    refetchInterval: 15_000,
  })

  if (isLoading) return <p>Loading statistics…</p>
  if (error || !data) return <p className="error-text">Failed to load statistics.</p>

  return (
    <div>
      <h1>Overview</h1>
      <div className="stat-grid">
        <StatCard label="Total users" value={data.total_users} />
        <StatCard label="Active wallets" value={data.active_wallets} />
        <StatCard label="Completed volume" value={data.completed_transaction_volume.toLocaleString()} />
        <StatCard label="Fraud — review" value={data.fraud_review_count} tone="yellow" />
        <StatCard label="Fraud — blocked" value={data.fraud_block_count} tone="red" />
      </div>

      <div className="panel-grid">
        <div className="panel">
          <h2>Transactions by status</h2>
          <BreakdownTable data={data.transactions_by_status} />
        </div>
        <div className="panel">
          <h2>Transactions by type</h2>
          <BreakdownTable data={data.transactions_by_type} />
        </div>
      </div>
    </div>
  )
}

function StatCard({ label, value, tone }: { label: string; value: number | string; tone?: 'yellow' | 'red' }) {
  return (
    <div className={`stat-card ${tone ? `stat-card-${tone}` : ''}`}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  )
}

function BreakdownTable({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data)
  if (entries.length === 0) return <p className="muted">No data yet.</p>
  return (
    <table>
      <tbody>
        {entries.map(([key, value]) => (
          <tr key={key}>
            <td>{key}</td>
            <td className="num">{value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
