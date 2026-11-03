"""TradingView Strategy Tester "List of Trades" CSV export.

Each trade appears as two rows (entry and exit) sharing a trade number. Header
names have changed between TradingView versions, so several spellings are
accepted: ``Trade #`` / ``Trade number``; ``Date/Time`` / ``Date and time``;
``Profit USD`` / ``Net P&L USD`` / ``Net PnL USD`` / ``P&L``; ``Contracts`` /
``Quantity`` / ``Qty`` / ``Size (qty)``. Times are in the chart's timezone, so
pass ``--source-tz``. The file has no symbol column; use ``--default-symbol``.
Rows whose exit is still open (signal ``Open``) are skipped.
"""

from __future__ import annotations

from datetime import tzinfo

from ..models import InputError, Trade, TradeHistory
from .common import norm, parse_datetime, parse_number, parse_side


def _find(headers: list[str], *names: str, prefix: bool = False) -> int | None:
    for name in names:
        for i, h in enumerate(headers):
            if h == name or (prefix and h.startswith(name)):
                return i
    return None


def is_tradingview_header(row: list[str]) -> bool:
    h = [norm(x) for x in row]
    return (
        _find(h, "trade #", "trade number", "trade no.") is not None
        and _find(h, "type") is not None
    )


def parse_tradingview(
    rows: list[list[str]],
    tz: tzinfo,
    *,
    fmt: str | None = None,
    decimal_comma: bool = False,
    source: str = "",
    default_symbol: str = "UNKNOWN",
    **_: object,
) -> TradeHistory:
    h = [norm(x) for x in rows[0]]
    i_num = _find(h, "trade #", "trade number", "trade no.")
    i_type = _find(h, "type")
    i_sig = _find(h, "signal")
    i_time = _find(h, "date/time", "date and time", "date", "time", prefix=True)
    i_price = _find(h, "price", prefix=True)
    i_qty = _find(h, "contracts", "quantity", "qty", "size (qty)", "size", prefix=True)
    i_pnl = _find(h, "net p&l", "net pnl", "profit", "p&l", "pnl", prefix=True)
    if i_pnl is not None and h[i_pnl].endswith("%"):
        i_pnl = next(
            (
                i
                for i, x in enumerate(h)
                if i != i_pnl
                and not x.endswith("%")
                and x.startswith(("net p&l", "net pnl", "profit", "p&l"))
            ),
            None,
        )
    if i_num is None or i_type is None or i_time is None or i_pnl is None:
        raise InputError(
            "TradingView export needs Trade #, Type, Date/Time and a P&L column "
            f"(header was {rows[0]!r})"
        )

    def get(row: list[str], i: int | None) -> str:
        return row[i] if i is not None and i < len(row) else ""

    entries: dict[str, list[str]] = {}
    exits: dict[str, list[str]] = {}
    order: list[str] = []
    for row in rows[1:]:
        num = get(row, i_num)
        typ = norm(get(row, i_type))
        if not num:
            continue
        if typ.startswith("entry"):
            entries[num] = row
        elif typ.startswith("exit"):
            exits[num] = row
        if num not in order:
            order.append(num)
    trades: list[Trade] = []
    skipped_open = 0
    for num in order:
        ex = exits.get(num)
        en = entries.get(num)
        if ex is None or norm(get(ex, i_sig)) == "open" or not get(ex, i_time):
            skipped_open += 1
            continue
        side = parse_side(norm(get(ex, i_type)).replace("exit", "").strip())
        price_in = get(en, i_price) if en else ""
        price_out = get(ex, i_price)
        qty = get(ex, i_qty) or (get(en, i_qty) if en else "")
        trades.append(
            Trade(
                id=num,
                symbol=default_symbol.upper(),
                side=side,
                open_time=parse_datetime(get(en, i_time), tz, fmt=fmt, field=f"entry of #{num}")
                if en and get(en, i_time)
                else None,
                close_time=parse_datetime(get(ex, i_time), tz, fmt=fmt, field=f"exit of #{num}"),
                pnl=parse_number(
                    get(ex, i_pnl) or (get(en, i_pnl) if en else ""),
                    field=f"P&L of #{num}",
                    decimal_comma=decimal_comma,
                ),
                volume=parse_number(qty, decimal_comma=decimal_comma) if qty else None,
                entry_price=parse_number(price_in, decimal_comma=decimal_comma)
                if price_in
                else None,
                exit_price=parse_number(price_out, decimal_comma=decimal_comma)
                if price_out
                else None,
            )
        )
    notes = [
        "TradingView: times are in the chart's timezone (set --source-tz); the export "
        "has no symbol column (set --default-symbol)."
    ]
    if skipped_open:
        notes.append(f"TradingView: skipped {skipped_open} trade(s) without a closed exit row.")
    return TradeHistory(trades=trades, format="tradingview", source=source, notes=notes)
