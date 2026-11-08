export function Badge({ text, tone }: { text: string; tone: 'green' | 'red' | 'yellow' | 'gray' | 'blue' }) {
  return <span className={`badge badge-${tone}`}>{text}</span>
}

const WALLET_TONE: Record<string, 'green' | 'red' | 'gray'> = {
  active: 'green',
  frozen: 'red',
  closed: 'gray',
}

const TXN_TONE: Record<string, 'green' | 'red' | 'yellow' | 'gray' | 'blue'> = {
  completed: 'green',
  pending: 'yellow',
  processing: 'blue',
  failed: 'red',
  reversed: 'gray',
  refunded: 'gray',
}

const FRAUD_TONE: Record<string, 'green' | 'red' | 'yellow'> = {
  allow: 'green',
  review: 'yellow',
  block: 'red',
}

export function WalletStatusBadge({ status }: { status: string }) {
  return <Badge text={status} tone={WALLET_TONE[status] ?? 'gray'} />
}

export function TransactionStatusBadge({ status }: { status: string }) {
  return <Badge text={status} tone={TXN_TONE[status] ?? 'gray'} />
}

export function FraudActionBadge({ action }: { action: string }) {
  return <Badge text={action} tone={FRAUD_TONE[action] ?? 'gray'} />
}
