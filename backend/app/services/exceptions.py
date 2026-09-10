"""
Domain exceptions for trade rejection. The API layer maps these to the
professional financial-system error codes required by spec section 58
(INSUFFICIENT_FUNDS, MARKET_PAUSED, etc.) rather than generic 400s.
"""
from app.models.base import RejectionReason


class TradeRejected(Exception):
    def __init__(self, reason: RejectionReason, message: str):
        self.reason = reason
        self.message = message
        super().__init__(message)


class DuplicateIdempotencyKey(Exception):
    """
    Raised internally when a unique-constraint violation on idempotency_key
    is caught. The service layer catches this and fetches+returns the
    original trade instead of propagating an error - the whole point of
    idempotency is that retries are safe, not that they fail loudly.
    """
    pass
