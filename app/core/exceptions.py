from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class AppException(Exception):
    """Base application exception carrying an HTTP status code."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    detail: str = "Bad request"

    def __init__(self, detail: str | None = None) -> None:
        if detail:
            self.detail = detail
        super().__init__(self.detail)


class NotFoundError(AppException):
    status_code = status.HTTP_404_NOT_FOUND
    detail = "Resource not found"


class ConflictError(AppException):
    status_code = status.HTTP_409_CONFLICT
    detail = "Resource already exists"


class UnauthorizedError(AppException):
    status_code = status.HTTP_401_UNAUTHORIZED
    detail = "Could not validate credentials"


class ForbiddenError(AppException):
    status_code = status.HTTP_403_FORBIDDEN
    detail = "You do not have permission to perform this action"


class RateLimitError(AppException):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    detail = "Too many requests"


class InsufficientFundsError(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    detail = "Insufficient funds"


class WalletNotActiveError(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    detail = "Wallet is not active"


class TransferLimitExceededError(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    detail = "Transfer limit exceeded"


class FraudBlockedError(AppException):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    detail = "Transaction blocked by fraud rules"


class IdempotencyConflictError(AppException):
    status_code = status.HTTP_409_CONFLICT
    detail = "Idempotency key was already used with a different request body"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(_: Request, exc: AppException) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=headers)
