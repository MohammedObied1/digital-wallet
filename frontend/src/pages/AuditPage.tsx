import { Fragment, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { AuditLogOut, Page } from '../api/types'
import { Pager } from '../components/Pager'
import { useAuth } from '../auth/useAuth'

export default function AuditPage() {
  const { user: me } = useAuth()
  const [page, setPage] = useState(1)
  const [entityType, setEntityType] = useState('')
  const [action, setAction] = useState('')
  const [expanded, setExpanded] = useState<number | null>(null)

  const { data, isLoading, error } = useQuery({
    queryKey: ['audit', page, entityType, action],
    enabled: me?.role === 'admin',
    queryFn: async () =>
      (
        await api.get<Page<AuditLogOut>>('/audit', {
          params: { page, size: 20, entity_type: entityType || undefined, action: action || undefined },
        })
      ).data,
  })

  if (me?.role !== 'admin') {
    return <p className="muted">The audit log is restricted to admin accounts.</p>
  }

  return (
    <div>
      <h1>Audit Log</h1>
      <div className="filter-bar">
        <input
          placeholder="Entity type (e.g. wallet)"
          value={entityType}
          onChange={(e) => {
            setPage(1)
            setEntityType(e.target.value)
          }}
        />
        <input
          placeholder="Action (e.g. wallet.freeze)"
          value={action}
          onChange={(e) => {
            setPage(1)
            setAction(e.target.value)
          }}
        />
      </div>

      {isLoading && <p>Loading…</p>}
      {error && <p className="error-text">Failed to load audit log.</p>}
      {data && (
        <>
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Actor</th>
                <th>Action</th>
                <th>Entity</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((entry) => (
                <Fragment key={entry.id}>
                  <tr className="clickable" onClick={() => setExpanded(expanded === entry.id ? null : entry.id)}>
                    <td>{entry.id}</td>
                    <td>{entry.actor_user_id ?? 'system'}</td>
                    <td>{entry.action}</td>
                    <td>
                      {entry.entity_type}#{entry.entity_id}
                    </td>
                    <td>{new Date(entry.created_at).toLocaleString()}</td>
                  </tr>
                  {expanded === entry.id && (
                    <tr className="detail-row">
                      <td colSpan={5}>
                        <div className="detail-cols">
                          <div>
                            <strong>Before</strong>
                            <pre>{JSON.stringify(entry.before, null, 2)}</pre>
                          </div>
                          <div>
                            <strong>After</strong>
                            <pre>{JSON.stringify(entry.after, null, 2)}</pre>
                          </div>
                        </div>
                        <div className="muted">IP: {entry.ip_address ?? 'n/a'}</div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
              {data.items.length === 0 && (
                <tr>
                  <td colSpan={5} className="muted">
                    No audit entries match these filters.
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
