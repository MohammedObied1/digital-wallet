import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'

const ACCESS_KEY = 'wallet_admin_access_token'
const REFRESH_KEY = 'wallet_admin_refresh_token'

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY)
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY)
}

export function setTokens(access: string, refresh: string): void {
  localStorage.setItem(ACCESS_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

export const api = axios.create({ baseURL: '/api/v1' })

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAccessToken()
  if (token) {
    config.headers.set('Authorization', `Bearer ${token}`)
  }
  return config
})

let refreshPromise: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) throw new Error('No refresh token')
  const { data } = await axios.post('/api/v1/auth/refresh', { refresh_token: refreshToken })
  setTokens(data.access_token, data.refresh_token)
  return data.access_token as string
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined
    if (error.response?.status === 401 && original && !original._retry && getRefreshToken()) {
      original._retry = true
      try {
        refreshPromise ??= refreshAccessToken()
        const newAccess = await refreshPromise
        refreshPromise = null
        original.headers.set('Authorization', `Bearer ${newAccess}`)
        return api.request(original)
      } catch (refreshError) {
        refreshPromise = null
        clearTokens()
        window.location.href = '/login'
        return Promise.reject(refreshError)
      }
    }
    return Promise.reject(error)
  },
)

export function apiErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((d) => (typeof d === 'string' ? d : d?.msg)).join(', ')
    return error.message
  }
  return String(error)
}
