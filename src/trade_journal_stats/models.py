"""Core data types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


class InputError(ValueError):
    """Raised when an input file cannot be read as a trade history."""


@dataclass(frozen=True)
class Trade:
    """One closed trade (a round trip), with a net result in account currency.

    ``pnl`` is the *net* result: profit after commission and swap/financing.
    ``side`` is ``"long"``, ``"short"`` or ``""`` when the file does not say.
    Times are timezone-aware. ``open_time`` may be ``None`` for formats that
    only carry a close time.
    """

    close_time: datetime
    pnl: float
    symbol: str = "UNKNOWN"
    side: str = ""
    id: str = ""
    open_time: datetime | None = None
    volume: float | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    stop_price: float | None = None
    risk: float | None = None  # money at risk when the trade was opened (positive)

    @property
    def r_multiple(self) -> float | None:
        """Result in R, or ``None`` when no risk information is available.

        Uses ``risk`` (money) when present: ``pnl / risk``. Otherwise, when entry,
        exit and stop prices are all known, the price-based R
        ``direction * (exit - entry) / |entry - stop|`` (gross of costs).
        """
        if self.risk is not None and self.risk > 0:
            return self.pnl / self.risk
        if (
            self.stop_price is not None
            and self.entry_price is not None
            and self.exit_price is not None
            and self.side in ("long", "short")
        ):
            dist = abs(self.entry_price - self.stop_price)
            if dist > 0:
                sign = 1.0 if self.side == "long" else -1.0
                return sign * (self.exit_price - self.entry_price) / dist
        return None

    @property
    def entry_time(self) -> datetime:
        """Open time when known, otherwise close time."""
        return self.open_time or self.close_time


@dataclass
class TradeHistory:
    trades: list[Trade]
    format: str
    source: str = ""
    notes: list[str] = field(default_factory=list)
