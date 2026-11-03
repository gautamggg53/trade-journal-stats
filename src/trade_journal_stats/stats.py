"""Performance statistics. Every formula is documented in docs/METRICS.md."""

from __future__ import annotations

import math
from collections import OrderedDict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone, tzinfo

from .models import Trade

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# Fixed UTC windows keyed on the trade's entry hour. They ignore daylight saving,
# so treat them as rough buckets, not exchange hours.
SESSIONS: tuple[tuple[str, int, int], ...] = (
    ("Asia", 0, 7),
    ("London", 7, 12),
    ("London/NY overlap", 12, 16),
    ("New York", 16, 21),
    ("Off-hours", 21, 24),
)

# R-multiple buckets: [lower, upper) with open ends.
R_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("< -2R", -math.inf, -2.0),
    ("-2R to -1R", -2.0, -1.0),
    ("-1R to 0R", -1.0, 0.0),
    ("0R to 1R", 0.0, 1.0),
    ("1R to 2R", 1.0, 2.0),
    ("2R to 3R", 2.0, 3.0),
    (">= 3R", 3.0, math.inf),
)

TRADING_DAYS_PER_YEAR = 252


def _r(x: float | None, nd: int = 10) -> float | None:
    if x is None or math.isinf(x) or math.isnan(x):
        return None
    return round(x, nd)


def session_of(dt: datetime) -> str:
    hour = dt.astimezone(timezone.utc).hour
    for name, lo, hi in SESSIONS:
        if lo <= hour < hi:
            return name
    raise AssertionError("unreachable")  # pragma: no cover


@dataclass
class GroupStats:
    trades: int
    wins: int
    losses: int
    win_rate: float | None
    net_pnl: float
    avg_pnl: float | None
    profit_factor: float | None


@dataclass
class Drawdown:
    amount: float = 0.0
    pct: float | None = None
    peak_time: str | None = None
    trough_time: str | None = None
    recovery_time: str | None = None
    duration_days: float | None = None
    recovered: bool = True


@dataclass
class Report:
    trades: int
    wins: int
    losses: int
    breakeven: int
    net_pnl: float
    gross_profit: float
    gross_loss: float
    win_rate: float | None
    avg_win: float | None
    avg_loss: float | None
    payoff_ratio: float | None
    profit_factor: float | None
    expectancy: float | None
    expectancy_r: float | None
    trades_with_r: int
    r_distribution: dict[str, int]
    largest_win: float | None
    largest_loss: float | None
    max_drawdown: Drawdown
    max_win_streak: int
    max_loss_streak: int
    current_streak: int
    sharpe: float | None
    sortino: float | None
    daily_periods: int
    start_balance: float | None
    end_balance: float | None
    first_trade: str | None
    last_trade: str | None
    timezone: str
    by_symbol: dict[str, GroupStats] = field(default_factory=dict)
    by_weekday: dict[str, GroupStats] = field(default_factory=dict)
    by_hour: dict[str, GroupStats] = field(default_factory=dict)
    by_session: dict[str, GroupStats] = field(default_factory=dict)
    by_side: dict[str, GroupStats] = field(default_factory=dict)
    monthly: dict[str, dict[str, float]] = field(default_factory=dict)
    equity_curve: list[tuple[str, float]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def group_stats(trades: Sequence[Trade]) -> GroupStats:
    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gp, gl = sum(wins), sum(losses)
    return GroupStats(
        trades=len(pnls),
        wins=len(wins),
        losses=len(losses),
        win_rate=_r(len(wins) / len(pnls)) if pnls else None,
        net_pnl=_r(sum(pnls)) or 0.0,
        avg_pnl=_r(sum(pnls) / len(pnls)) if pnls else None,
        profit_factor=_r(gp / -gl) if gl < 0 else None,
    )


def _grouped(
    trades: Iterable[Trade], key: Callable[[Trade], str], order: Sequence[str] | None = None
) -> dict[str, GroupStats]:
    buckets: dict[str, list[Trade]] = {}
    for t in trades:
        buckets.setdefault(key(t), []).append(t)
    keys = [k for k in order if k in buckets] if order else sorted(buckets)
    return OrderedDict((k, group_stats(buckets[k])) for k in keys)


def streaks(pnls: Sequence[float]) -> tuple[int, int, int]:
    """Return (longest win streak, longest loss streak, current streak).

    The current streak is positive for wins and negative for losses. A
    break-even trade (P&L exactly 0) ends any streak.
    """
    best_w = best_l = cur = 0
    for p in pnls:
        if p > 0:
            cur = cur + 1 if cur > 0 else 1
        elif p < 0:
            cur = cur - 1 if cur < 0 else -1
        else:
            cur = 0
        best_w = max(best_w, cur)
        best_l = max(best_l, -cur)
    return best_w, best_l, cur


def max_drawdown(points: Sequence[tuple[datetime, float]]) -> Drawdown:
    """Largest peak-to-trough fall of a closed-equity curve.

    ``points`` is a time-ordered list of (time, equity). The duration runs from
    the peak to the first later point at or above that peak, or to the last
    point if the curve never recovered. ``pct`` is relative to the peak and is
    only set when the peak is positive.
    """
    if not points:
        return Drawdown()
    peak_i = 0
    best_amt = 0.0
    best_peak_i = best_trough_i = -1
    for i, (_, v) in enumerate(points):
        if v > points[peak_i][1]:
            peak_i = i
            continue
        dd = points[peak_i][1] - v
        if dd > best_amt + 1e-12:
            best_amt, best_peak_i, best_trough_i = dd, peak_i, i
    if best_peak_i < 0:
        return Drawdown()
    peak_t, peak_v = points[best_peak_i]
    end_t = points[-1][0]
    recovery: datetime | None = None
    for t, v in points[best_trough_i + 1 :]:
        if v >= peak_v - 1e-12:
            recovery = end_t = t
            break
    return Drawdown(
        amount=_r(best_amt) or 0.0,
        pct=_r(best_amt / peak_v * 100) if peak_v > 0 else None,
        peak_time=peak_t.isoformat(),
        trough_time=points[best_trough_i][0].isoformat(),
        recovery_time=recovery.isoformat() if recovery else None,
        duration_days=_r((end_t - peak_t).total_seconds() / 86400, 4),
        recovered=recovery is not None,
    )


def daily_returns(trades: Sequence[Trade], balance: float, tz: tzinfo) -> list[float]:
    """Daily returns on equity for the period covered by ``trades``.

    Days are calendar days in ``tz`` keyed on close time. Every Monday-Friday
    between the first and last close date is included (0% if nothing closed),
    plus any Saturday or Sunday on which a trade closed. Each day's return is
    that day's P&L divided by equity at the start of the day.
    """
    if not trades:
        return []
    by_day: dict[date, float] = {}
    for t in trades:
        d = t.close_time.astimezone(tz).date()
        by_day[d] = by_day.get(d, 0.0) + t.pnl
    first, last = min(by_day), max(by_day)
    out: list[float] = []
    equity = balance
    d = first
    while d <= last:
        if d in by_day or d.weekday() < 5:
            pnl = by_day.get(d, 0.0)
            out.append(pnl / equity if equity > 0 else 0.0)
            equity += pnl
        d += timedelta(days=1)
    return out


def sharpe_sortino(returns: Sequence[float]) -> tuple[float | None, float | None]:
    """Annualised Sharpe and Sortino ratios with a 0% risk-free rate and target.

    Sharpe = mean / sample stdev * sqrt(252). Sortino = mean / downside
    deviation * sqrt(252), where downside deviation = sqrt(mean(min(r, 0)^2))
    over all periods. ``None`` when undefined (fewer than 2 periods or zero
    deviation).
    """
    n = len(returns)
    if n < 2:
        return None, None
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / (n - 1)
    ann = math.sqrt(TRADING_DAYS_PER_YEAR)
    sharpe = mean / math.sqrt(var) * ann if var > 0 else None
    down = math.sqrt(sum(min(r, 0.0) ** 2 for r in returns) / n)
    sortino = mean / down * ann if down > 0 else None
    return _r(sharpe, 6), _r(sortino, 6)


def r_distribution(rs: Iterable[float]) -> dict[str, int]:
    dist = OrderedDict((name, 0) for name, _, _ in R_BUCKETS)
    for r in rs:
        for name, lo, hi in R_BUCKETS:
            if lo <= r < hi:
                dist[name] += 1
                break
    return dist


def filter_trades(
    trades: Iterable[Trade],
    *,
    start: date | None = None,
    end: date | None = None,
    symbols: Iterable[str] | None = None,
    tz: tzinfo = timezone.utc,
) -> list[Trade]:
    """Keep trades whose close date (in ``tz``) is within [start, end] and symbol matches."""
    wanted = {s.upper() for s in symbols} if symbols else None
    out = []
    for t in trades:
        d = t.close_time.astimezone(tz).date()
        if start and d < start:
            continue
        if end and d > end:
            continue
        if wanted is not None and t.symbol.upper() not in wanted:
            continue
        out.append(t)
    return out


def compute_report(
    trades: Sequence[Trade],
    *,
    tz: tzinfo = timezone.utc,
    balance: float | None = None,
    risk_per_trade: float | None = None,
) -> Report:
    """Compute every statistic for ``trades`` (any order; sorted by close time here).

    ``balance`` is the account balance before the first trade; it enables
    percentage drawdown and Sharpe/Sortino. ``risk_per_trade`` is a fixed money
    risk applied to trades that carry no risk or stop of their own.
    """
    ts = sorted(trades, key=lambda t: (t.close_time, t.id))
    notes: list[str] = []
    pnls = [t.pnl for t in ts]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    n = len(pnls)
    gp, gl = sum(wins), sum(losses)
    avg_win = gp / len(wins) if wins else None
    avg_loss = gl / len(losses) if losses else None

    rs: list[float] = []
    for t in ts:
        r = t.r_multiple
        if r is None and risk_per_trade and risk_per_trade > 0:
            r = t.pnl / risk_per_trade
        if r is not None:
            rs.append(r)
    if n and not rs:
        notes.append(
            "No per-trade risk or stop found, so R statistics are not available "
            "(add a risk/stop_price column or pass --risk-per-trade)."
        )
    elif rs and len(rs) < n:
        notes.append(f"R statistics use the {len(rs)} of {n} trades that have risk data.")

    start_eq = balance if balance is not None else 0.0
    points: list[tuple[datetime, float]] = []
    equity = start_eq
    if ts:
        points.append((min(t.entry_time for t in ts), equity))
    for t in ts:
        equity += t.pnl
        points.append((t.close_time, equity))
    dd = max_drawdown(points)
    if balance is None:
        dd.pct = None  # a percentage of P&L-from-zero would be meaningless
        notes.append(
            "No --balance given: drawdown is in money only, and Sharpe/Sortino are not computed."
        )

    best_w, best_l, cur = streaks(pnls)
    sharpe = sortino = None
    periods = 0
    if balance is not None and balance > 0:
        rets = daily_returns(ts, balance, tz)
        periods = len(rets)
        sharpe, sortino = sharpe_sortino(rets)

    def local(t: Trade) -> datetime:
        return t.entry_time.astimezone(tz)

    monthly: dict[str, dict[str, float]] = OrderedDict()
    for t in ts:
        c = t.close_time.astimezone(tz)
        row = monthly.setdefault(str(c.year), OrderedDict())
        row[MONTHS[c.month - 1]] = round(row.get(MONTHS[c.month - 1], 0.0) + t.pnl, 10)
    for row in monthly.values():
        row["Total"] = round(sum(v for k, v in row.items() if k != "Total"), 10)

    sides = {"long": "Long", "short": "Short", "": "Unknown"}
    return Report(
        trades=n,
        wins=len(wins),
        losses=len(losses),
        breakeven=n - len(wins) - len(losses),
        net_pnl=_r(sum(pnls)) or 0.0,
        gross_profit=_r(gp) or 0.0,
        gross_loss=_r(gl) or 0.0,
        win_rate=_r(len(wins) / n) if n else None,
        avg_win=_r(avg_win),
        avg_loss=_r(avg_loss),
        payoff_ratio=_r(avg_win / -avg_loss) if avg_win is not None and avg_loss else None,
        profit_factor=_r(gp / -gl) if gl < 0 else None,
        expectancy=_r(sum(pnls) / n) if n else None,
        expectancy_r=_r(sum(rs) / len(rs)) if rs else None,
        trades_with_r=len(rs),
        r_distribution=r_distribution(rs),
        largest_win=_r(max(wins)) if wins else None,
        largest_loss=_r(min(losses)) if losses else None,
        max_drawdown=dd,
        max_win_streak=best_w,
        max_loss_streak=best_l,
        current_streak=cur,
        sharpe=sharpe,
        sortino=sortino,
        daily_periods=periods,
        start_balance=balance,
        end_balance=_r(equity) if balance is not None else None,
        first_trade=ts[0].close_time.astimezone(tz).isoformat() if ts else None,
        last_trade=ts[-1].close_time.astimezone(tz).isoformat() if ts else None,
        timezone=str(tz),
        by_symbol=_grouped(ts, lambda t: t.symbol),
        by_weekday=_grouped(ts, lambda t: WEEKDAYS[local(t).weekday()], WEEKDAYS),
        by_hour=_grouped(ts, lambda t: f"{local(t).hour:02d}"),
        by_session=_grouped(ts, lambda t: session_of(t.entry_time), [s[0] for s in SESSIONS]),
        by_side=_grouped(ts, lambda t: sides.get(t.side, "Unknown"), ["Long", "Short", "Unknown"]),
        monthly=monthly,
        equity_curve=[(p[0].astimezone(tz).isoformat(), _r(p[1]) or 0.0) for p in points],
        notes=notes,
    )
