"""Input formats and auto-detection."""

from __future__ import annotations

from datetime import tzinfo
from pathlib import Path

from ..models import InputError, TradeHistory
from .common import decode, get_tz, looks_like_html, read_csv_rows, read_html_rows
from .ctrader import is_ctrader_header, parse_ctrader
from .generic import is_generic_header, parse_generic
from .mt5 import is_mt5_header, parse_mt5
from .tradingview import is_tradingview_header, parse_tradingview

FORMATS = ("generic", "mt5", "ctrader", "tradingview")


def detect_format(rows: list[list[str]], is_html: bool) -> str:
    """Guess the format from the table headers."""
    if is_html:
        if any(is_mt5_header(r) for r in rows):
            return "mt5"
        raise InputError(
            "HTML file without an MT5 Positions table; only MT5 HTML reports are supported"
        )
    header = rows[0] if rows else []
    if is_tradingview_header(header):
        return "tradingview"
    if is_mt5_header(header):
        return "mt5"
    if is_ctrader_header(header):
        return "ctrader"
    if is_generic_header(header):
        return "generic"
    raise InputError(
        "could not recognise the file format from its header "
        f"{header!r}; pass --format (one of {', '.join(FORMATS)})"
    )


def load_trades(
    path: str | Path,
    *,
    fmt: str = "auto",
    source_tz: str | tzinfo | None = None,
    date_format: str | None = None,
    decimal_comma: bool = False,
    default_symbol: str = "UNKNOWN",
) -> TradeHistory:
    """Read a trade history file and return closed trades sorted by close time."""
    p = Path(path)
    try:
        text = decode(p.read_bytes())
    except OSError as exc:
        raise InputError(f"cannot read {p}: {exc.strerror or exc}") from exc
    tz = source_tz if isinstance(source_tz, tzinfo) else get_tz(source_tz)
    is_html = looks_like_html(text)
    rows = read_html_rows(text) if is_html else read_csv_rows(text)
    if not rows:
        raise InputError(f"{p} contains no rows")
    if fmt == "auto":
        fmt = detect_format(rows, is_html)
    kwargs = {"fmt": date_format, "decimal_comma": decimal_comma, "source": str(p)}
    if fmt == "generic":
        hist = parse_generic(rows, tz, default_symbol=default_symbol, **kwargs)
    elif fmt == "mt5":
        hist = parse_mt5(rows, tz, is_html=is_html, **kwargs)
    elif fmt == "ctrader":
        hist = parse_ctrader(rows, tz, **kwargs)
    elif fmt == "tradingview":
        hist = parse_tradingview(rows, tz, default_symbol=default_symbol, **kwargs)
    else:
        raise InputError(f"unknown format {fmt!r}; choose from auto, {', '.join(FORMATS)}")
    hist.trades.sort(key=lambda t: (t.close_time, t.id))
    return hist


__all__ = ["FORMATS", "detect_format", "load_trades"]
