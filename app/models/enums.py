import enum


class UserRole(str, enum.Enum):
    USER = "user"
    SUPPORT = "support"
    ADMIN = "admin"


class WalletStatus(str, enum.Enum):
    ACTIVE = "active"
    FROZEN = "frozen"
    CLOSED = "closed"


class Currency(str, enum.Enum):
    ILS = "ILS"
    USD = "USD"
    EUR = "EUR"


class LedgerEntryType(str, enum.Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class TransactionType(str, enum.Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"
    PAYMENT_REQUEST = "payment_request"
    REFUND = "refund"
    REVERSAL = "reversal"


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REVERSED = "reversed"
    REFUNDED = "refunded"


class PaymentRequestStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class FraudAction(str, enum.Enum):
    ALLOW = "allow"
    REVIEW = "review"
    BLOCK = "block"


class OutboxStatus(str, enum.Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"
