"""Render a Report as a terminal table, JSON, CSV or a self-contained HTML page."""

from __future__ import annotations

import csv
import html
import io
import json
from collections.abc import Sequence
from dataclasses import asdict

from .stats import MONTHS, GroupStats, Report


def _money(x: float | None) -> str:
    return "n/a" if x is None else f"{x:,.2f}"


def _num(x: float | None, nd: int = 2) -> str:
    return "n/a" if x is None else f"{x:,.{nd}f}"


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]], left: int = 1) -> str:
    """Plain-text table; the first ``left`` columns are left-aligned, the rest right."""
    widths = [max(len(str(c)) for c in col) for col in zip(headers, *rows, strict=False)]

    def line(cells: Sequence[str]) -> str:
        out = [
            f"{c:<{w}}" if i < left else f"{c:>{w}}"
            for i, (c, w) in enumerate(zip(cells, widths, strict=False))
        ]
        return "  ".join(out).rstrip()

    out = [line(headers), "  ".join("-" * w for w in widths)]
    out.extend(line([str(c) for c in r]) for r in rows)
    return "\n".join(out)


def summary_rows(r: Report) -> list[tuple[str, str]]:
    dd = r.max_drawdown
    dd_text = _money(dd.amount)
    if dd.pct is not None:
        dd_text += f" ({dd.pct:.2f}%)"
    dur = "n/a"
    if dd.duration_days is not None:
        dur = f"{dd.duration_days:.1f} days" + ("" if dd.recovered else " (not recovered)")
    streak = r.current_streak
    if streak:
        word = (
            ("win" if abs(streak) == 1 else "wins")
            if streak > 0
            else ("loss" if abs(streak) == 1 else "losses")
        )
        cur = f"{abs(streak)} {word}"
    else:
        cur = "none"
    rows = [
        ("Trades", f"{r.trades} ({r.wins} W / {r.losses} L / {r.breakeven} BE)"),
        ("Net P&L", _money(r.net_pnl)),
        ("Gross profit / loss", f"{_money(r.gross_profit)} / {_money(r.gross_loss)}"),
        ("Win rate", _pct(r.win_rate)),
        ("Avg win / avg loss", f"{_money(r.avg_win)} / {_money(r.avg_loss)}"),
        ("Payoff ratio", _num(r.payoff_ratio)),
        ("Profit factor", _num(r.profit_factor)),
        ("Expectancy / trade", _money(r.expectancy)),
        (
            "Expectancy (R)",
            "n/a"
            if r.expectancy_r is None
            else f"{r.expectancy_r:.2f}R over {r.trades_with_r} trades",
        ),
        ("Largest win / loss", f"{_money(r.largest_win)} / {_money(r.largest_loss)}"),
        ("Max drawdown (closed)", dd_text),
        ("Drawdown duration", dur),
        ("Longest win / loss streak", f"{r.max_win_streak} / {r.max_loss_streak}"),
        ("Current streak", cur),
        ("Sharpe (daily, ann.)", _num(r.sharpe)),
        ("Sortino (daily, ann.)", _num(r.sortino)),
    ]
    if r.start_balance is not None:
        rows.append(("Balance start / end", f"{_money(r.start_balance)} / {_money(r.end_balance)}"))
    return rows


def _group_rows(groups: dict[str, GroupStats]) -> list[list[str]]:
    return [
        [
            k,
            str(g.trades),
            _pct(g.win_rate),
            _money(g.net_pnl),
            _money(g.avg_pnl),
            _num(g.profit_factor),
        ]
        for k, g in groups.items()
    ]


GROUP_HEADERS = ("", "Trades", "Win%", "Net P&L", "Avg", "PF")
SECTIONS = (
    ("By symbol", "by_symbol"),
    ("By side", "by_side"),
    ("By session (UTC)", "by_session"),
    ("By weekday", "by_weekday"),
    ("By hour", "by_hour"),
)


def render_text(r: Report, *, title: str = "Trade journal stats") -> str:
    parts = [title, "=" * len(title)]
    if r.first_trade:
        parts.append(f"Period: {r.first_trade[:10]} to {r.last_trade[:10]} ({r.timezone})")
    parts.append("")
    parts.append(_table(("Metric", "Value"), summary_rows(r), left=2))
    if r.trades_with_r:
        parts += [
            "",
            "R-multiple distribution",
            _table(("Bucket", "Trades"), [(k, str(v)) for k, v in r.r_distribution.items()]),
        ]
    for label, attr in SECTIONS:
        groups = getattr(r, attr)
        if groups:
            parts += ["", label, _table(GROUP_HEADERS, _group_rows(groups))]
    if r.monthly:
        cols = [m for m in MONTHS if any(m in row for row in r.monthly.values())]
        rows = [
            [y, *[_money(row[m]) if m in row else "" for m in cols], _money(row["Total"])]
            for y, row in r.monthly.items()
        ]
        parts += ["", "Monthly P&L", _table(("Year", *cols, "Total"), rows)]
    if r.notes:
        parts += ["", "Notes:"] + [f"- {n}" for n in r.notes]
    return "\n".join(parts) + "\n"


def render_json(r: Report) -> str:
    return json.dumps(r.to_dict(), indent=2, allow_nan=False) + "\n"


def render_csv(r: Report) -> str:
    """Long-format CSV: section, group, metric, value."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["section", "group", "metric", "value"])
    d = r.to_dict()
    for key, value in d.items():
        if isinstance(value, (int, float, str)) or value is None:
            w.writerow(["summary", "", key, "" if value is None else value])
    for key, value in d["max_drawdown"].items():
        w.writerow(["max_drawdown", "", key, "" if value is None else value])
    for bucket, count in r.r_distribution.items():
        w.writerow(["r_distribution", bucket, "trades", count])
    for _, attr in SECTIONS:
        for group, gs in getattr(r, attr).items():
            for metric, value in asdict(gs).items():
                w.writerow([attr, group, metric, "" if value is None else value])
    for year, row in r.monthly.items():
        for month, value in row.items():
            w.writerow(["monthly", year, month, value])
    return buf.getvalue()


def equity_svg(points: Sequence[tuple[str, float]], width: int = 800, height: int = 260) -> str:
    """Inline SVG line chart of the equity curve (x = trade number, y = equity)."""
    if len(points) < 2:
        return "<p>Not enough trades for an equity curve.</p>"
    pad = 40
    values = [v for _, v in points]
    lo, hi = min(values), max(values)
    span = hi - lo or 1.0
    n = len(values) - 1

    def xy(i: int, v: float) -> str:
        x = pad + (width - 2 * pad) * i / n
        y = height - pad - (height - 2 * pad) * (v - lo) / span
        return f"{x:.1f},{y:.1f}"

    poly = " ".join(xy(i, v) for i, v in enumerate(values))
    base_y = height - pad - (height - 2 * pad) * (values[0] - lo) / span
    esc = html.escape
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="Closed-trade equity curve">'
        f'<rect width="{width}" height="{height}" fill="#fff"/>'
        f'<line x1="{pad}" y1="{base_y:.1f}" x2="{width - pad}" y2="{base_y:.1f}" '
        'stroke="#bbb" stroke-dasharray="4 4"/>'
        f'<polyline fill="none" stroke="#1f6feb" stroke-width="2" points="{poly}"/>'
        f'<text x="{pad}" y="{pad - 12}" font-size="12" fill="#555">max {esc(_money(hi))}</text>'
        f'<text x="{pad}" y="{height - 12}" font-size="12" fill="#555">min {esc(_money(lo))}'
        f" &#183; {n} trades &#183; {esc(points[0][0][:10])} to {esc(points[-1][0][:10])}</text>"
        "</svg>"
    )


def _html_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    e = html.escape
    head = "".join(f"<th>{e(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{e(str(c))}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_html(r: Report, *, title: str = "Trade journal stats") -> str:
    """A single HTML file with inline CSS and SVG; it loads nothing from the network."""
    e = html.escape
    parts = [
        "<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>",
        f"<title>{e(title)}</title><style>",
        "body{font-family:system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;"
        "color:#222}table{border-collapse:collapse;margin:.5rem 0 1.5rem}"
        "th,td{border:1px solid #ddd;padding:4px 8px;text-align:right}"
        "th:first-child,td:first-child{text-align:left}th{background:#f4f4f4}"
        "svg{width:100%;height:auto;border:1px solid #ddd}.muted{color:#666;font-size:.9em}",
        "</style></head><body>",
        f"<h1>{e(title)}</h1>",
    ]
    if r.first_trade:
        parts.append(
            f"<p class='muted'>{e(r.first_trade[:10])} to {e(r.last_trade[:10])} "
            f"({e(r.timezone)}). Generated by trade-journal-stats. "
            "Not financial advice.</p>"
        )
    parts += [
        "<h2>Equity curve (closed trades)</h2>",
        equity_svg(r.equity_curve),
        "<h2>Summary</h2>",
        _html_table(("Metric", "Value"), summary_rows(r)),
    ]
    if r.trades_with_r:
        parts += [
            "<h2>R-multiple distribution</h2>",
            _html_table(("Bucket", "Trades"), [(k, str(v)) for k, v in r.r_distribution.items()]),
        ]
    for label, attr in SECTIONS:
        groups = getattr(r, attr)
        if groups:
            parts += [f"<h2>{e(label)}</h2>", _html_table(GROUP_HEADERS, _group_rows(groups))]
    if r.monthly:
        cols = [m for m in MONTHS if any(m in row for row in r.monthly.values())]
        rows = [
            [y, *[_money(row[m]) if m in row else "" for m in cols], _money(row["Total"])]
            for y, row in r.monthly.items()
        ]
        parts += ["<h2>Monthly P&amp;L</h2>", _html_table(("Year", *cols, "Total"), rows)]
    if r.notes:
        parts.append("<h2>Notes</h2><ul>" + "".join(f"<li>{e(n)}</li>" for n in r.notes) + "</ul>")
    parts.append("</body></html>\n")
    return "".join(parts)
