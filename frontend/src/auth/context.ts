import { createContext } from 'react'
import type { UserOut } from '../api/types'

export interface AuthState {
  user: UserOut | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

export const AuthContext = createContext<AuthState | null>(null)
