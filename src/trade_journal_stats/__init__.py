"""Performance statistics for closed-trade histories (MT5, cTrader, TradingView, CSV)."""

from .models import InputError, Trade, TradeHistory
from .parsers import FORMATS, load_trades
from .stats import Report, compute_report

__all__ = [
    "FORMATS",
    "InputError",
    "Report",
    "Trade",
    "TradeHistory",
    "compute_report",
    "load_trades",
]
__version__ = "0.1.0"
