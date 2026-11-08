"""Development seed data — local/demo use only, never run against a production database.

Goes through the same service layer the API uses (auth_service, wallet_service,
transaction_service, payment_request_service) rather than inserting rows directly, so every
seeded financial record satisfies the same ledger/limit/idempotency invariants real traffic would.
The one deliberate exception is FraudRule/TransferLimitPolicy config rows, which have no
create-through-service concept beyond a plain insert (there's no business rule to violate by
inserting one directly).

Run: `python -m scripts.seed` (or `make seed`). Safe to re-run — each step is skipped if the data
it would create already exists, so seeding twice does not duplicate wallets or transactions.

Demo credentials (development only — never reuse these anywhere real):
    admin1   / Passw0rd123   (role: admin)
    support1 / Passw0rd123   (role: support)
    alice    / Passw0rd123   (role: user)
    bob      / Passw0rd123   (role: user)
    carol    / Passw0rd123   (role: user, holds a frozen wallet)
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, init_db
from app.models import Currency, FraudAction, FraudRule, User, UserRole, Wallet
from app.schemas.payment_request import PaymentRequestCreate
from app.schemas.user import UserRegister
from app.schemas.wallet import WalletCreate
from app.services import auth_service, payment_request_service, transaction_service, wallet_service

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("seed")

DEMO_PASSWORD = "Passw0rd123"  # noqa: S105 - development-only seed credential, documented above


def _get_or_create_user(db: Session, *, username: str, email: str, full_name: str, role: UserRole) -> User:
    existing = db.scalar(select(User).where(User.username == username))
    if existing:
        return existing
    user = auth_service.register(db, UserRegister(email=email, username=username, password=DEMO_PASSWORD, full_name=full_name))
    if role != UserRole.USER:
        user.role = role
        db.commit()
        db.refresh(user)
    logger.info("  created user %-10s (%s)", username, role.value)
    return user


def _get_or_create_wallet(db: Session, user: User, currency: str, label: str | None = None) -> Wallet:
    existing = db.scalar(select(Wallet).where(Wallet.user_id == user.id, Wallet.currency == Currency(currency)))
    if existing:
        return existing
    wallet = wallet_service.create_wallet(db, user, WalletCreate(currency=Currency(currency), label=label))
    logger.info("  created %s wallet #%s for %s", currency, wallet.id, user.username)
    return wallet


def _idem() -> str:
    return str(uuid.uuid4())


def seed() -> None:
    init_db()
    db = SessionLocal()
    try:
        logger.info("Users:")
        admin = _get_or_create_user(db, username="admin1", email="admin@example.com", full_name="Ada Admin", role=UserRole.ADMIN)
        _get_or_create_user(db, username="support1", email="support@example.com", full_name="Sam Support", role=UserRole.SUPPORT)
        alice = _get_or_create_user(db, username="alice", email="alice@example.com", full_name="Alice Anders", role=UserRole.USER)
        bob = _get_or_create_user(db, username="bob", email="bob@example.com", full_name="Bob Baker", role=UserRole.USER)
        carol = _get_or_create_user(db, username="carol", email="carol@example.com", full_name="Carol Chen", role=UserRole.USER)

        logger.info("Wallets:")
        alice_ils = _get_or_create_wallet(db, alice, "ILS", "Main")
        bob_ils = _get_or_create_wallet(db, bob, "ILS", "Main")
        bob_usd = _get_or_create_wallet(db, bob, "USD", "Travel")
        carol_ils = _get_or_create_wallet(db, carol, "ILS", "Main")

        if alice_ils.balance == 0:
            logger.info("Transactions:")
            transaction_service.deposit(db, alice_ils, 1000, "Initial demo deposit", alice)
            db.commit()

            transaction_service.transfer(db, alice_ils, bob_ils, 150, "Rent split", alice)
            db.commit()

            transaction_service.deposit(db, bob_usd, 500, "Initial USD deposit", bob)
            db.commit()
            transaction_service.withdraw(db, bob_usd, 50, "ATM withdrawal", bob)
            db.commit()

            # A transaction that fails validation on purpose (insufficient funds), so the demo
            # data includes a realistic FAILED transaction for the transaction explorer.
            try:
                transaction_service.transfer(db, carol_ils, alice_ils, 9999, "Doomed transfer", carol)
            except Exception:  # noqa: BLE001 - expected: carol_ils has a zero balance
                db.rollback()
            else:
                db.commit()

            # A completed transfer that then gets partially refunded.
            refund_source = transaction_service.transfer(db, alice_ils, bob_ils, 100, "Shared dinner", alice)
            db.commit()
            transaction_service.refund(db, refund_source, alice, amount=40)
            db.commit()

            logger.info("Payment request:")
            pr = payment_request_service.create(
                db, bob, PaymentRequestCreate(requester_wallet_id=bob_ils.id, payer_wallet_id=alice_ils.id, amount=25, description="Coffee")
            )
            payment_request_service.accept(db, pr.id, alice)

            logger.info("Freezing carol's wallet (support/admin demo action):")
            wallet_service.freeze_wallet(db, carol_ils.id, admin)
        else:
            logger.info("Transactions/payment request/freeze already seeded, skipping.")

        logger.info("Fraud rules:")
        if not db.scalar(select(FraudRule).where(FraudRule.name == "Large transfer review")):
            db.add(
                FraudRule(
                    name="Large transfer review",
                    rule_type="large_amount",
                    config={"threshold": 500},
                    action=FraudAction.REVIEW,
                    is_active=True,
                )
            )
            db.commit()
            logger.info("  created 'Large transfer review' rule (threshold=500, action=review)")

            # Trigger it once so the fraud dashboard has a sample event to show.
            bonus_wallet = _get_or_create_wallet(db, alice, "EUR", "Bonus")
            transaction_service.deposit(db, bonus_wallet, 2000, "Bonus deposit", alice)
            db.commit()
            eur_receiver = _get_or_create_wallet(db, bob, "EUR", "Bonus")
            transaction_service.transfer(db, bonus_wallet, eur_receiver, 800, "Large transfer (triggers review)", alice)
            db.commit()
        else:
            logger.info("  already seeded, skipping.")

        logger.info("\nDone. Demo credentials (development only, password '%s' for all):", DEMO_PASSWORD)
        for username, role in [("admin1", "admin"), ("support1", "support"), ("alice", "user"), ("bob", "user"), ("carol", "user")]:
            logger.info("  %-10s (%s)", username, role)
    finally:
        db.close()


if __name__ == "__main__":
    seed()
