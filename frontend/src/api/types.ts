export type UserRole = 'user' | 'support' | 'admin'
export type WalletStatus = 'active' | 'frozen' | 'closed'
export type Currency = 'ILS' | 'USD' | 'EUR'
export type TransactionType = 'deposit' | 'withdrawal' | 'transfer' | 'payment_request' | 'refund' | 'reversal'
export type TransactionStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'reversed' | 'refunded'
export type FraudAction = 'allow' | 'review' | 'block'

// The API serializes money as a decimal string (e.g. "100.00"), never a JSON number — see
// ARCHITECTURE.md's "Money representation" section. Treat it as opaque text in the UI; only
// convert to Number at the point of display formatting, never for further arithmetic.
export type Money = string

export interface UserOut {
  id: number
  email: string
  username: string
  full_name: string | null
  role: UserRole
  is_active: boolean
}

export interface WalletOut {
  id: number
  user_id: number
  currency: Currency
  status: WalletStatus
  balance: Money
  available_balance: Money
  label: string | null
}

export interface TransactionOut {
  id: number
  type: TransactionType
  status: TransactionStatus
  sender_wallet_id: number | null
  receiver_wallet_id: number | null
  amount: Money
  currency: string
  description: string | null
  related_transaction_id: number | null
  created_at: string
  completed_at: string | null
}

export interface FraudRuleOut {
  id: number
  name: string
  rule_type: string
  config: Record<string, unknown>
  action: FraudAction
  is_active: boolean
}

export interface FraudEventOut {
  id: number
  transaction_id: number
  rule_id: number | null
  risk_score: number
  action: FraudAction
  details: Record<string, unknown>
  created_at: string
}

export interface AuditLogOut {
  id: number
  actor_user_id: number | null
  action: string
  entity_type: string
  entity_id: string | null
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  ip_address: string | null
  created_at: string
}

export interface Page<T> {
  items: T[]
  total: number
  page: number
  size: number
  pages: number
}

export function formatMoney(value: Money): string {
  return Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

export interface AdminStats {
  total_users: number
  active_wallets: number
  transactions_by_status: Record<string, number>
  transactions_by_type: Record<string, number>
  completed_transaction_volume: number
  fraud_review_count: number
  fraud_block_count: number
}
