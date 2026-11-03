"""cTrader History tab export (CSV).

Column names follow the cTrader help pages for the History tab: ID, Symbol,
Opening direction, Opening time, Closing time, Entry price, Closing price,
Closing quantity, Swap, Commission(s), Gross <currency>, Net <currency>.
Time headers often carry the zone, e.g. ``Closing time (UTC+1)``, and money
headers the account currency, e.g. ``Net EUR``. Users can hide and reorder
columns, so columns are matched by name.
"""

from __future__ import annotations

import re
from datetime import tzinfo

from ..models import InputError, Trade, TradeHistory
from .common import get_tz, norm, parse_datetime, parse_number, parse_side


def _find(headers: list[str], *prefixes: str, exclude: tuple[str, ...] = ()) -> int | None:
    for p in prefixes:
        for i, h in enumerate(headers):
            if h.startswith(p) and not any(h.startswith(x) for x in exclude):
                return i
    return None


def is_ctrader_header(row: list[str]) -> bool:
    headers = [norm(h) for h in row]
    return _find(headers, "closing time") is not None and (
        _find(headers, "opening direction") is not None or _find(headers, "net") is not None
    )


def header_tz(header: str, default: tzinfo) -> tzinfo:
    m = re.search(r"\(\s*(?:utc|gmt)\s*([+-]\d{1,2}(?::?\d{2})?)?\s*\)", header, re.IGNORECASE)
    if not m:
        return default
    return get_tz(m.group(1) or "UTC")


def parse_ctrader(
    rows: list[list[str]],
    tz: tzinfo,
    *,
    fmt: str | None = None,
    decimal_comma: bool = False,
    source: str = "",
    **_: object,
) -> TradeHistory:
    if not rows:
        raise InputError("the file is empty")
    raw = rows[0]
    h = [norm(x) for x in raw]
    i_close = _find(h, "closing time", "close time")
    i_open = _find(h, "opening time", "open time")
    net_usd = ("net usd", "net (usd)")
    i_net = _find(h, "net", exclude=net_usd)
    i_net_usd = _find(h, *net_usd)
    i_gross = _find(h, "gross", exclude=("gross usd", "gross (usd)"))
    if i_gross is None:
        i_gross = _find(h, "gross")
    i_comm = _find(h, "commission")
    i_swap = _find(h, "swap")
    i_sym = _find(h, "symbol")
    i_dir = _find(h, "opening direction", "direction")
    i_qty = _find(h, "closing quantity", "quantity")
    i_id = _find(h, "id", exclude=("ident",))
    i_entry = _find(h, "entry price")
    i_exit = _find(h, "closing price")
    if i_close is None:
        raise InputError(
            "cTrader export has no 'Closing time' column; enable it in the "
            "History tab (right-click a column header) and export again"
        )
    notes: list[str] = []
    i_pnl = i_net if i_net is not None else i_net_usd
    use_gross = False
    if i_pnl is None:
        if i_gross is None:
            raise InputError(
                "cTrader export has no Net or Gross column; enable 'Net' in the "
                "History tab and export again"
            )
        i_pnl, use_gross = i_gross, True
        notes.append("cTrader: no Net column, so net = Gross + Commission + Swap.")
    elif i_net is None:
        notes.append("cTrader: using the 'Net USD' column.")
    tz_close = header_tz(raw[i_close], tz)
    tz_open = header_tz(raw[i_open], tz) if i_open is not None else tz
    if tz_close is not tz:
        notes.append(f"cTrader: timezone taken from the column header {raw[i_close]!r}.")

    def get(row: list[str], i: int | None) -> str:
        return row[i] if i is not None and i < len(row) else ""

    trades: list[Trade] = []
    for n, row in enumerate(rows[1:], start=2):
        close_raw = get(row, i_close)
        if not close_raw:
            continue
        pnl = parse_number(
            get(row, i_pnl), field=f"net P&L on row {n}", decimal_comma=decimal_comma
        )
        if use_gross:
            pnl += parse_number(get(row, i_comm), empty=0.0, decimal_comma=decimal_comma)
            pnl += parse_number(get(row, i_swap), empty=0.0, decimal_comma=decimal_comma)
        open_raw = get(row, i_open)
        qty = get(row, i_qty)
        entry = get(row, i_entry)
        exit_ = get(row, i_exit)
        trades.append(
            Trade(
                id=get(row, i_id) or str(n - 1),
                symbol=(get(row, i_sym) or "UNKNOWN").upper(),
                side=parse_side(get(row, i_dir)),
                open_time=parse_datetime(open_raw, tz_open, fmt=fmt, field=f"opening time row {n}")
                if open_raw
                else None,
                close_time=parse_datetime(
                    close_raw, tz_close, fmt=fmt, field=f"closing time row {n}"
                ),
                pnl=round(pnl, 10),
                volume=parse_number(qty.split()[0], decimal_comma=decimal_comma) if qty else None,
                entry_price=parse_number(entry, decimal_comma=decimal_comma) if entry else None,
                exit_price=parse_number(exit_, decimal_comma=decimal_comma) if exit_ else None,
            )
        )
    return TradeHistory(trades=trades, format="ctrader", source=source, notes=notes)
