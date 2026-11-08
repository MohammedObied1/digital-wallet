import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import type { Page, UserOut } from '../api/types'
import { Pager } from '../components/Pager'
import { useAuth } from '../auth/useAuth'

export default function UsersPage() {
  const [page, setPage] = useState(1)
  const { user: me } = useAuth()
  const queryClient = useQueryClient()

  const { data, isLoading, error } = useQuery({
    queryKey: ['users', page],
    queryFn: async () => (await api.get<Page<UserOut>>('/users', { params: { page, size: 20 } })).data,
  })

  const toggleActive = useMutation({
    mutationFn: async (u: UserOut) => api.post(`/users/${u.id}/${u.is_active ? 'deactivate' : 'activate'}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['users'] }),
  })

  return (
    <div>
      <h1>Users</h1>
      {isLoading && <p>Loading…</p>}
      {error && <p className="error-text">Failed to load users.</p>}
      {data && (
        <>
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Username</th>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((u) => (
                <tr key={u.id}>
                  <td>{u.id}</td>
                  <td>{u.username}</td>
                  <td>{u.email}</td>
                  <td>
                    <span className={`role-badge role-${u.role}`}>{u.role}</span>
                  </td>
                  <td>{u.is_active ? <span className="badge badge-green">active</span> : <span className="badge badge-red">inactive</span>}</td>
                  <td>
                    <button
                      className="btn-secondary"
                      disabled={me?.role !== 'admin' || toggleActive.isPending}
                      onClick={() => toggleActive.mutate(u)}
                    >
                      {u.is_active ? 'Deactivate' : 'Activate'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pager page={data.page} pages={data.pages} onChange={setPage} />
        </>
      )}
    </div>
  )
}
