"""The documented generic CSV format (one row per closed trade).

Required columns: ``close_time`` and ``pnl`` (net result in account currency).
Optional: ``id``, ``symbol``, ``side`` (long/short/buy/sell), ``open_time``,
``volume``, ``entry_price``, ``exit_price``, ``stop_price``, ``risk`` (money at
risk, positive). Column names are case-insensitive; a few aliases are accepted
(see ``ALIASES``). Unknown columns are ignored.
"""

from __future__ import annotations

from datetime import tzinfo

from ..models import InputError, Trade, TradeHistory
from .common import norm, parse_datetime, parse_number, parse_side

ALIASES: dict[str, tuple[str, ...]] = {
    "close_time": ("close_time", "close time", "exit_time", "exit time", "closed", "time"),
    "pnl": ("pnl", "net_pnl", "net pnl", "net p&l", "p&l", "profit", "net profit", "net"),
    "id": ("id", "ticket", "trade_id", "trade id"),
    "symbol": ("symbol", "instrument", "ticker", "market"),
    "side": ("side", "direction", "type"),
    "open_time": ("open_time", "open time", "entry_time", "entry time", "opened"),
    "volume": ("volume", "size", "qty", "quantity", "lots"),
    "entry_price": ("entry_price", "entry price", "open_price", "open price", "entry"),
    "exit_price": ("exit_price", "exit price", "close_price", "close price", "exit"),
    "stop_price": ("stop_price", "stop price", "stop", "sl", "stop_loss", "stop loss"),
    "risk": ("risk", "risk_amount", "initial_risk", "initial risk"),
}


def map_columns(header: list[str]) -> dict[str, int]:
    names = [norm(h) for h in header]
    out: dict[str, int] = {}
    for key, aliases in ALIASES.items():
        for alias in aliases:
            if alias in names:
                out[key] = names.index(alias)
                break
    return out


def is_generic_header(header: list[str]) -> bool:
    cols = map_columns(header)
    return "close_time" in cols and "pnl" in cols


def _opt_num(row: list[str], i: int | None, field: str, dc: bool) -> float | None:
    if i is None or i >= len(row) or not row[i].strip():
        return None
    return parse_number(row[i], field=field, decimal_comma=dc)


def parse_generic(
    rows: list[list[str]],
    tz: tzinfo,
    *,
    fmt: str | None = None,
    decimal_comma: bool = False,
    source: str = "",
    default_symbol: str = "UNKNOWN",
) -> TradeHistory:
    if not rows:
        raise InputError("the file is empty")
    cols = map_columns(rows[0])
    missing = [k for k in ("close_time", "pnl") if k not in cols]
    if missing:
        raise InputError(
            "generic CSV needs columns close_time and pnl; missing: "
            + ", ".join(missing)
            + f" (header was {rows[0]!r})"
        )
    trades: list[Trade] = []
    for n, row in enumerate(rows[1:], start=2):

        def cell(key: str, row: list[str] = row) -> str:
            i = cols.get(key)
            return row[i] if i is not None and i < len(row) else ""

        where = f"row {n}"
        open_raw = cell("open_time")
        risk = _opt_num(row, cols.get("risk"), f"risk on {where}", decimal_comma)
        trades.append(
            Trade(
                id=cell("id") or str(n - 1),
                symbol=(cell("symbol") or default_symbol).upper(),
                side=parse_side(cell("side")),
                open_time=parse_datetime(open_raw, tz, fmt=fmt, field=f"open_time on {where}")
                if open_raw
                else None,
                close_time=parse_datetime(
                    cell("close_time"), tz, fmt=fmt, field=f"close_time on {where}"
                ),
                pnl=parse_number(cell("pnl"), field=f"pnl on {where}", decimal_comma=decimal_comma),
                volume=_opt_num(row, cols.get("volume"), f"volume on {where}", decimal_comma),
                entry_price=_opt_num(
                    row, cols.get("entry_price"), f"entry_price on {where}", decimal_comma
                ),
                exit_price=_opt_num(
                    row, cols.get("exit_price"), f"exit_price on {where}", decimal_comma
                ),
                stop_price=_opt_num(
                    row, cols.get("stop_price"), f"stop_price on {where}", decimal_comma
                ),
                risk=abs(risk) if risk is not None else None,
            )
        )
    return TradeHistory(trades=trades, format="generic", source=source)
