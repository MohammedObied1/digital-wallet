import { useEffect, useState, type ReactNode } from 'react'
import { api, clearTokens, getAccessToken, setTokens } from '../api/client'
import type { UserOut } from '../api/types'
import { AuthContext } from './context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null)
  const [loading, setLoading] = useState(true)

  async function loadMe() {
    try {
      const { data } = await api.get<UserOut>('/auth/me')
      setUser(data)
    } catch {
      setUser(null)
    } finally {
      setLoading(false)
    }
  }

  // Session restore on first mount: check for a stored token and validate it against the API.
  // This is the canonical "fetch on mount" effect — there is no synchronous value to derive
  // instead, since it depends on an API round trip, so the setState calls inside loadMe() are
  // intentional here despite the linter's general caution about setState-in-effect.
  useEffect(() => {
    if (getAccessToken()) {
      loadMe()
    } else {
      setLoading(false)
    }
  }, [])

  async function login(username: string, password: string) {
    const form = new URLSearchParams()
    form.set('username', username)
    form.set('password', password)
    const { data } = await api.post('/auth/login', form, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    })
    setTokens(data.access_token, data.refresh_token)
    await loadMe()
  }

  function logout() {
    clearTokens()
    setUser(null)
  }

  return <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>
}
