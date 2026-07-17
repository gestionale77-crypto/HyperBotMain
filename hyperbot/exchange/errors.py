from __future__ import annotations


class HyperLiquidError(Exception):
    """Base exception for Hyperliquid client errors."""


class AuthenticationError(HyperLiquidError):
    """Raised when authentication fails."""


class RateLimitError(HyperLiquidError):
    """Raised when exchange rate limit is exceeded."""


class OrderPlacementError(HyperLiquidError):
    """Raised when an order cannot be placed."""


class WebSocketConnectionError(HyperLiquidError):
    """Raised when websocket connection fails."""
