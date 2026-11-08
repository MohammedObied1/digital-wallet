from fastapi import APIRouter

from app.api.v1 import admin, audit, auth, fraud, health, payment_requests, transactions, users, wallets

api_router = APIRouter()
api_router.include_router(health.versioned_router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(wallets.router)
api_router.include_router(transactions.router)
api_router.include_router(payment_requests.router)
api_router.include_router(fraud.router)
api_router.include_router(audit.router)
api_router.include_router(admin.router)
