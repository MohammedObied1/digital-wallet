import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, apiErrorMessage } from '../api/client'
import type { FraudEventOut, FraudRuleOut, Page } from '../api/types'
import { Pager } from '../components/Pager'
import { FraudActionBadge } from '../components/Badge'
import { useAuth } from '../auth/useAuth'

// Must match the keys fraud_service.py's `_EVALUATORS` dict actually checks — a rule created
// with any other rule_type is silently never evaluated (fraud_service.evaluate() skips unknown
// types rather than erroring, so this dashboard is the only guard against that typo class).
const RULE_TYPES = [
  { value: 'large_amount', label: 'Large amount', configKey: 'threshold', placeholder: 'Threshold (default 5000)' },
  {
    value: 'transfer_velocity',
    label: 'Transfer velocity',
    configKey: 'max_transactions',
    placeholder: 'Max transactions per window (default 5)',
  },
  {
    value: 'new_recipient_large_amount',
    label: 'New recipient, large amount',
    configKey: 'min_amount',
    placeholder: 'Minimum amount (default 1000)',
  },
] as const

export default function FraudPage() {
  const { user: me } = useAuth()
  const queryClient = useQueryClient()
  const [eventsPage, setEventsPage] = useState(1)

  const rulesQuery = useQuery({
    queryKey: ['fraud-rules'],
    queryFn: async () => (await api.get<FraudRuleOut[]>('/fraud/rules')).data,
  })

  const eventsQuery = useQuery({
    queryKey: ['fraud-events', eventsPage],
    queryFn: async () => (await api.get<Page<FraudEventOut>>('/fraud/events', { params: { page: eventsPage, size: 20 } })).data,
  })

  const deactivateRule = useMutation({
    mutationFn: async (id: number) => api.post(`/fraud/rules/${id}/deactivate`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['fraud-rules'] }),
  })

  const [newRule, setNewRule] = useState({ name: '', rule_type: RULE_TYPES[0].value as string, action: 'review', configValue: '' })
  const [createError, setCreateError] = useState<string | null>(null)
  const selectedRuleType = RULE_TYPES.find((rt) => rt.value === newRule.rule_type) ?? RULE_TYPES[0]

  const createRule = useMutation({
    mutationFn: async () =>
      api.post('/fraud/rules', {
        name: newRule.name,
        rule_type: newRule.rule_type,
        action: newRule.action,
        config: newRule.configValue ? { [selectedRuleType.configKey]: Number(newRule.configValue) } : {},
      }),
    onSuccess: () => {
      setNewRule({ name: '', rule_type: RULE_TYPES[0].value, action: 'review', configValue: '' })
      queryClient.invalidateQueries({ queryKey: ['fraud-rules'] })
    },
    onError: (err) => setCreateError(apiErrorMessage(err)),
  })

  return (
    <div>
      <h1>Fraud &amp; Risk</h1>

      <div className="panel">
        <h2>Rules</h2>
        {rulesQuery.data && (
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Name</th>
                <th>Type</th>
                <th>Action</th>
                <th>Config</th>
                <th>Active</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {rulesQuery.data.map((r) => (
                <tr key={r.id}>
                  <td>{r.id}</td>
                  <td>{r.name}</td>
                  <td>{r.rule_type}</td>
                  <td>
                    <FraudActionBadge action={r.action} />
                  </td>
                  <td>
                    <code>{JSON.stringify(r.config)}</code>
                  </td>
                  <td>{r.is_active ? 'yes' : 'no'}</td>
                  <td>
                    {r.is_active && (
                      <button
                        className="btn-secondary"
                        disabled={me?.role !== 'admin' || deactivateRule.isPending}
                        onClick={() => deactivateRule.mutate(r.id)}
                      >
                        Deactivate
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {me?.role === 'admin' && (
          <form
            className="inline-form"
            onSubmit={(e) => {
              e.preventDefault()
              setCreateError(null)
              createRule.mutate()
            }}
          >
            <input placeholder="Rule name" value={newRule.name} onChange={(e) => setNewRule({ ...newRule, name: e.target.value })} required />
            <select
              value={newRule.rule_type}
              onChange={(e) => setNewRule({ ...newRule, rule_type: e.target.value, configValue: '' })}
            >
              {RULE_TYPES.map((rt) => (
                <option key={rt.value} value={rt.value}>
                  {rt.label}
                </option>
              ))}
            </select>
            <select value={newRule.action} onChange={(e) => setNewRule({ ...newRule, action: e.target.value })}>
              <option value="allow">Allow</option>
              <option value="review">Review</option>
              <option value="block">Block</option>
            </select>
            <input
              placeholder={selectedRuleType.placeholder}
              value={newRule.configValue}
              onChange={(e) => setNewRule({ ...newRule, configValue: e.target.value })}
            />
            <button type="submit" disabled={createRule.isPending}>
              Add rule
            </button>
          </form>
        )}
        {createError && <div className="error-text">{createError}</div>}
      </div>

      <div className="panel">
        <h2>Recent fraud events</h2>
        {eventsQuery.data && (
          <>
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Transaction</th>
                  <th>Rule</th>
                  <th>Risk score</th>
                  <th>Action</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {eventsQuery.data.items.map((e) => (
                  <tr key={e.id}>
                    <td>{e.id}</td>
                    <td>{e.transaction_id}</td>
                    <td>{e.rule_id ?? '—'}</td>
                    <td>{e.risk_score.toFixed(2)}</td>
                    <td>
                      <FraudActionBadge action={e.action} />
                    </td>
                    <td>{new Date(e.created_at).toLocaleString()}</td>
                  </tr>
                ))}
                {eventsQuery.data.items.length === 0 && (
                  <tr>
                    <td colSpan={6} className="muted">
                      No fraud events recorded.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
            <Pager page={eventsQuery.data.page} pages={eventsQuery.data.pages} onChange={setEventsPage} />
          </>
        )}
      </div>
    </div>
  )
}
