"""Command-line interface: ``trade-stats HISTORY_FILE [options]``."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from . import __version__
from .models import InputError
from .output import render_csv, render_html, render_json, render_text
from .parsers import FORMATS, load_trades
from .parsers.common import get_tz
from .stats import compute_report, filter_trades


def _date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected YYYY-MM-DD, got {value!r}") from exc


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="trade-stats",
        description="Performance statistics for a closed-trade history "
        "(generic CSV, MT5 report, cTrader CSV, TradingView List of Trades).",
        epilog="Not financial advice. See docs/METRICS.md for every formula.",
    )
    p.add_argument("file", help="trade history file (CSV or MT5 HTML report)")
    p.add_argument(
        "--format",
        default="auto",
        choices=("auto", *FORMATS),
        help="input format (default: auto-detect from the header)",
    )
    p.add_argument(
        "--source-tz",
        default="UTC",
        help="timezone of naive timestamps in the file, e.g. 'Europe/Athens' or "
        "'+02:00' (default: UTC)",
    )
    p.add_argument(
        "--tz",
        default=None,
        help="timezone for dates, weekday/hour breakdowns, filters and the monthly "
        "table (default: same as --source-tz)",
    )
    p.add_argument(
        "--date-format", help="strptime format for timestamps, e.g. '%%m/%%d/%%Y %%H:%%M'"
    )
    p.add_argument("--decimal-comma", action="store_true", help="numbers use ',' as decimal mark")
    p.add_argument(
        "--default-symbol", default="UNKNOWN", help="symbol for files without one (TradingView)"
    )
    p.add_argument("--from", dest="start", type=_date, help="first close date to include")
    p.add_argument("--to", dest="end", type=_date, help="last close date to include")
    p.add_argument("--symbol", action="append", help="only these symbols (repeatable)")
    p.add_argument(
        "--balance", type=float, help="starting balance; enables drawdown %% and Sharpe/Sortino"
    )
    p.add_argument(
        "--risk-per-trade",
        type=float,
        help="fixed money risk for trades without their own risk/stop (enables R)",
    )
    out = p.add_argument_group("output (default: terminal table)")
    out.add_argument(
        "--json",
        nargs="?",
        const="-",
        metavar="PATH",
        help="write JSON to PATH, or stdout if no PATH",
    )
    out.add_argument(
        "--csv",
        nargs="?",
        const="-",
        metavar="PATH",
        help="write long-format CSV to PATH, or stdout if no PATH",
    )
    out.add_argument("--html", metavar="PATH", help="write a self-contained HTML report")
    out.add_argument("--title", default="Trade journal stats", help="report title")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def _write(path: str, text: str) -> None:
    if path == "-":
        sys.stdout.write(text)
    else:
        Path(path).write_text(text, encoding="utf-8")
        print(f"wrote {path}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        source_tz = get_tz(args.source_tz)
        tz = get_tz(args.tz) if args.tz else source_tz
        hist = load_trades(
            args.file,
            fmt=args.format,
            source_tz=source_tz,
            date_format=args.date_format,
            decimal_comma=args.decimal_comma,
            default_symbol=args.default_symbol,
        )
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.balance is not None and args.balance <= 0:
        print("error: --balance must be positive", file=sys.stderr)
        return 2
    trades = filter_trades(hist.trades, start=args.start, end=args.end, symbols=args.symbol, tz=tz)
    if not trades:
        print(
            f"error: no closed trades left after reading {len(hist.trades)} trade(s) from "
            f"{args.file} and applying filters",
            file=sys.stderr,
        )
        return 1
    report = compute_report(trades, tz=tz, balance=args.balance, risk_per_trade=args.risk_per_trade)
    report.notes = [
        f"Read {len(hist.trades)} trade(s) as format '{hist.format}'"
        + (f"; {len(trades)} after filters." if len(trades) != len(hist.trades) else "."),
        *hist.notes,
        *report.notes,
    ]
    wrote_machine = False
    if args.json:
        _write(args.json, render_json(report))
        wrote_machine = args.json == "-"
    if args.csv:
        _write(args.csv, render_csv(report))
        wrote_machine = wrote_machine or args.csv == "-"
    if args.html:
        _write(args.html, render_html(report, title=args.title))
    if not wrote_machine:
        sys.stdout.write(render_text(report, title=args.title))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
