"""MetaTrader 5 "Trade History Report" (HTML, or its Positions table saved as CSV).

MT5 desktop: Toolbox -> History tab -> right-click -> Report -> HTML. The file is
usually UTF-16. Its "Positions" table has the columns Time, Position, Symbol,
Type, Volume, Price, S / L, T / P, Time, Price, Commission, Swap, Profit; the
first Time/Price pair is the open, the second the close.

The layout here follows public descriptions of the report. It has NOT been
checked against a real exported file; please open an issue with a redacted
sample if parsing fails. Times are broker server time with no zone: pass
``--source-tz``.
"""

from __future__ import annotations

from datetime import tzinfo

from ..models import InputError, Trade, TradeHistory
from .common import norm, parse_datetime, parse_number, parse_side

_SECTION_END = ("orders", "deals", "open positions", "working orders", "results", "summary")


def _index(header: list[str]) -> dict[str, list[int]]:
    idx: dict[str, list[int]] = {}
    for i, h in enumerate(header):
        key = norm(h).replace(" / ", "/").replace(" ", "")
        if key:
            idx.setdefault(key, []).append(i)
    return idx


def is_mt5_header(row: list[str]) -> bool:
    idx = _index(row)
    return (
        "position" in idx
        and "symbol" in idx
        and "volume" in idx
        and len(idx.get("time", [])) >= 2
        and "profit" in idx
    )


def parse_mt5(
    rows: list[list[str]],
    tz: tzinfo,
    *,
    fmt: str | None = None,
    decimal_comma: bool = False,
    source: str = "",
    is_html: bool = True,
    **_: object,
) -> TradeHistory:
    header: dict[str, list[int]] | None = None
    in_positions = not is_html
    trades: list[Trade] = []
    for row in rows:
        joined = norm(" ".join(c for c in row if c))
        if is_html and joined == "positions":
            in_positions = True
            continue
        if is_html and in_positions and header is not None and joined in _SECTION_END:
            break
        if not in_positions:
            continue
        if is_mt5_header(row):
            header = _index(row)
            continue
        if header is None:
            continue

        def cell(
            name: str, occ: int = 0, row: list[str] = row, header: dict[str, list[int]] = header
        ) -> str:
            pos = header.get(name, [])
            return row[pos[occ]] if len(pos) > occ and pos[occ] < len(row) else ""

        pid = cell("position")
        side = parse_side(cell("type"))
        if not pid or side == "":
            continue
        profit = parse_number(
            cell("profit"), field=f"profit of position {pid}", decimal_comma=decimal_comma
        )
        commission = parse_number(cell("commission"), empty=0.0, decimal_comma=decimal_comma)
        swap = parse_number(cell("swap"), empty=0.0, decimal_comma=decimal_comma)
        sl = parse_number(cell("s/l"), empty=0.0, decimal_comma=decimal_comma)
        trades.append(
            Trade(
                id=pid,
                symbol=cell("symbol").upper(),
                side=side,
                volume=parse_number(
                    cell("volume").split("/")[0],
                    field="volume",
                    empty=0.0,
                    decimal_comma=decimal_comma,
                ),
                open_time=parse_datetime(cell("time"), tz, fmt=fmt, field=f"open time of {pid}"),
                close_time=parse_datetime(
                    cell("time", 1), tz, fmt=fmt, field=f"close time of {pid}"
                ),
                entry_price=parse_number(cell("price"), empty=0.0, decimal_comma=decimal_comma),
                exit_price=parse_number(cell("price", 1), empty=0.0, decimal_comma=decimal_comma),
                stop_price=sl or None,
                pnl=round(profit + commission + swap, 10),
            )
        )
    if header is None:
        raise InputError(
            "no MT5 Positions table (Time, Position, Symbol, Type, Volume, ..., "
            "Profit) was found. Save the report from the History tab as HTML."
        )
    notes = [
        "MT5: net P&L = Profit + Commission + Swap. Times are broker server time; "
        "use --source-tz to set it.",
        "MT5: the S / L column is the stop at close (it may have been moved), so R "
        "values from it are approximate.",
    ]
    return TradeHistory(trades=trades, format="mt5", source=source, notes=notes)
