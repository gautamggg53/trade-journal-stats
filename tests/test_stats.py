"""Statistics on hand-computed examples. Expected values are worked out in comments."""

import math
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from trade_journal_stats import Trade, compute_report, load_trades
from trade_journal_stats.stats import (
    daily_returns,
    filter_trades,
    max_drawdown,
    r_distribution,
    session_of,
    sharpe_sortino,
    streaks,
)

UTC = timezone.utc


@pytest.fixture
def small(fx):
    return load_trades(fx / "generic_small.csv").trades


@pytest.fixture
def rep(small):
    return compute_report(small, balance=10_000)


def test_counts_and_pnl(rep):
    # P&L: +200, -100, -50, 0, +300, -150
    assert (rep.trades, rep.wins, rep.losses, rep.breakeven) == (6, 2, 3, 1)
    assert rep.net_pnl == 200
    assert rep.gross_profit == 500
    assert rep.gross_loss == -300
    assert rep.win_rate == pytest.approx(2 / 6)  # break-evens count in the denominator
    assert rep.largest_win == 300
    assert rep.largest_loss == -150


def test_averages_ratios_expectancy(rep):
    assert rep.avg_win == 250  # (200 + 300) / 2
    assert rep.avg_loss == -100  # (-100 - 50 - 150) / 3
    assert rep.payoff_ratio == 2.5  # 250 / 100
    assert rep.profit_factor == pytest.approx(500 / 300)
    assert rep.expectancy == pytest.approx(200 / 6)


def test_r_multiples(rep):
    # risk 100 each: R = 2, -1, -0.5, 0, 3, -1.5 -> mean 2/6
    assert rep.trades_with_r == 6
    assert rep.expectancy_r == pytest.approx(1 / 3)
    assert rep.r_distribution == {
        "< -2R": 0,
        "-2R to -1R": 1,
        "-1R to 0R": 2,
        "0R to 1R": 1,
        "1R to 2R": 0,
        "2R to 3R": 1,
        ">= 3R": 1,
    }


def test_drawdown(rep):
    # equity 10000 -> 10200 (peak, 01-05 10:00) -> 10100 -> 10050 (trough) -> 10050
    # -> 10350 (recovered 01-09 19:00) -> 10200 (a later 150 dip: equal, not larger)
    dd = rep.max_drawdown
    assert dd.amount == 150
    assert dd.pct == pytest.approx(150 / 10_200 * 100)
    assert dd.peak_time == "2026-01-05T10:00:00+00:00"
    assert dd.trough_time == "2026-01-06T16:00:00+00:00"
    assert dd.recovery_time == "2026-01-09T19:00:00+00:00"
    assert dd.duration_days == pytest.approx(4.375)  # 4 days 9 hours
    assert dd.recovered


def test_streaks(rep):
    # W L L BE W L
    assert (rep.max_win_streak, rep.max_loss_streak, rep.current_streak) == (1, 2, -1)


def test_streaks_function():
    assert streaks([]) == (0, 0, 0)
    assert streaks([1, 2, 3, -1, -1, 0, 5, 5]) == (3, 2, 2)
    assert streaks([-1, -2, -3]) == (0, 3, -3)


def test_breakdowns(rep):
    assert rep.by_symbol["EURUSD"].net_pnl == 450
    assert rep.by_symbol["GBPUSD"].net_pnl == -250
    assert rep.by_symbol["XAUUSD"].trades == 1
    assert list(rep.by_symbol) == ["EURUSD", "GBPUSD", "XAUUSD"]
    assert rep.by_side["Long"].net_pnl == 0  # 200 - 50 - 150
    assert rep.by_side["Short"].net_pnl == 200  # -100 + 0 + 300
    assert rep.by_side["Short"].profit_factor == 3.0
    assert rep.by_side["Long"].win_rate == pytest.approx(1 / 3)
    assert list(rep.by_weekday) == ["Mon", "Tue", "Wed", "Fri"]
    assert rep.by_weekday["Mon"].trades == 3
    assert rep.by_weekday["Mon"].net_pnl == -50
    assert rep.by_hour["08"].net_pnl == 200
    sessions = {k: v.trades for k, v in rep.by_session.items()}
    assert sessions == {"Asia": 1, "London": 2, "London/NY overlap": 2, "New York": 1}


def test_monthly(rep):
    assert rep.monthly == {"2026": {"Jan": 350, "Feb": -150, "Total": 200}}


def test_report_timezone_shifts_buckets(small):
    rep = compute_report(small, tz=ZoneInfo("Asia/Kolkata"))
    # 08:00 UTC -> 13:30 IST; session buckets stay on UTC.
    assert "13" in rep.by_hour and "08" not in rep.by_hour
    assert rep.by_session["London"].trades == 2
    assert rep.first_trade.endswith("+05:30")


def test_equity_curve(rep):
    values = [v for _, v in rep.equity_curve]
    assert values == [10000, 10200, 10100, 10050, 10050, 10350, 10200]
    assert rep.end_balance == 10200


def test_sharpe_sortino_hand_example():
    # mean 0.005, sample sd sqrt(5e-4/3), downside dev sqrt(1e-4/4) = 0.005
    s, so = sharpe_sortino([0.01, -0.01, 0.02, 0.0])
    assert s == pytest.approx(0.005 / math.sqrt(5e-4 / 3) * math.sqrt(252), rel=1e-6)
    assert so == pytest.approx(math.sqrt(252), rel=1e-6)


def test_sharpe_sortino_undefined():
    assert sharpe_sortino([0.01]) == (None, None)
    assert sharpe_sortino([0.01, 0.01]) == (None, None)  # zero deviation, no downside


def test_daily_returns_fill_weekdays(small):
    rets = daily_returns(small, 10_000, UTC)
    # 2026-01-05 .. 2026-02-02 has 21 weekdays; no weekend trades.
    assert len(rets) == 21
    assert rets[0] == pytest.approx(100 / 10_000)  # +200 - 100 on Monday
    assert rets[1] == pytest.approx(-50 / 10_100)
    assert rets[4] == pytest.approx(300 / 10_050)
    assert rets[-1] == pytest.approx(-150 / 10_350)
    assert sum(1 for r in rets if r == 0) == 17


def test_daily_returns_includes_weekend_trade_days():
    t = [
        Trade(close_time=datetime(2026, 1, 9, tzinfo=UTC), pnl=10),
        Trade(close_time=datetime(2026, 1, 10, tzinfo=UTC), pnl=10),  # Saturday
        Trade(close_time=datetime(2026, 1, 12, tzinfo=UTC), pnl=10),
    ]
    assert len(daily_returns(t, 1000, UTC)) == 3  # Fri, Sat, Mon (Sun skipped)


def test_report_sharpe_matches_definition(small, rep):
    rets = daily_returns(small, 10_000, UTC)
    n = len(rets)
    mean = sum(rets) / n
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (n - 1))
    assert rep.sharpe == pytest.approx(mean / sd * math.sqrt(252), rel=1e-5)
    assert rep.daily_periods == 21


def test_no_balance_disables_ratios(small):
    rep = compute_report(small)
    assert rep.sharpe is None and rep.sortino is None
    assert rep.max_drawdown.amount == 150
    assert rep.max_drawdown.pct is None
    assert any("No --balance" in n for n in rep.notes)


def test_drawdown_not_recovered():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    pts = [
        (t0, 0.0),
        (t0 + timedelta(days=1), 100.0),
        (t0 + timedelta(days=2), 40.0),
        (t0 + timedelta(days=4), 90.0),
    ]
    dd = max_drawdown(pts)
    assert dd.amount == 60
    assert not dd.recovered and dd.recovery_time is None
    assert dd.duration_days == 3  # peak day 1 -> last point day 4
    assert dd.pct == 60.0


def test_drawdown_monotonic_up_is_zero():
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    dd = max_drawdown([(t0, 0.0), (t0 + timedelta(hours=1), 5.0)])
    assert dd.amount == 0 and dd.peak_time is None
    assert max_drawdown([]).amount == 0


def test_drawdown_from_start():
    # First trade is a loss: the starting balance is the peak.
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    dd = max_drawdown(
        [(t0, 1000.0), (t0 + timedelta(days=1), 900.0), (t0 + timedelta(days=2), 1000.0)]
    )
    assert dd.amount == 100 and dd.pct == 10.0 and dd.duration_days == 2 and dd.recovered


def test_profit_factor_and_payoff_undefined_without_losses():
    t = [Trade(close_time=datetime(2026, 1, 1, tzinfo=UTC), pnl=10)]
    rep = compute_report(t)
    assert rep.profit_factor is None and rep.payoff_ratio is None and rep.avg_loss is None


def test_r_from_stops(fx):
    rep = compute_report(load_trades(fx / "generic_stops.csv").trades)
    # R = 2, -0.5, -1
    assert rep.expectancy_r == pytest.approx(0.5 / 3)
    assert rep.trades_with_r == 3


def test_risk_per_trade_fallback(small):
    stripped = [Trade(close_time=t.close_time, pnl=t.pnl) for t in small]
    rep = compute_report(stripped, risk_per_trade=50)
    assert rep.expectancy_r == pytest.approx((200 / 6) / 50)
    rep2 = compute_report(stripped)
    assert rep2.expectancy_r is None
    assert any("R statistics are not available" in n for n in rep2.notes)


def test_partial_r_note():
    t = [
        Trade(close_time=datetime(2026, 1, 1, tzinfo=UTC), pnl=10, risk=5),
        Trade(close_time=datetime(2026, 1, 2, tzinfo=UTC), pnl=-5),
    ]
    rep = compute_report(t)
    assert rep.trades_with_r == 1 and rep.expectancy_r == 2
    assert any("1 of 2" in n for n in rep.notes)


def test_r_multiple_edge_cases():
    base = {"close_time": datetime(2026, 1, 1, tzinfo=UTC), "pnl": 1.0}
    assert Trade(**base, entry_price=1, exit_price=2, stop_price=1, side="long").r_multiple is None
    assert Trade(**base, entry_price=1, exit_price=2, stop_price=0).r_multiple is None  # no side
    assert Trade(**base, risk=0).r_multiple is None


def test_r_distribution_edges():
    d = r_distribution([-2.0, -1.0, 0.0, 1.0, 2.0, 3.0, -5.0])
    assert list(d.values()) == [1, 1, 1, 1, 1, 1, 1]


def test_session_boundaries():
    def at(h):
        return datetime(2026, 1, 5, h, tzinfo=UTC)

    assert [session_of(at(h)) for h in (0, 6, 7, 11, 12, 15, 16, 20, 21, 23)] == [
        "Asia",
        "Asia",
        "London",
        "London",
        "London/NY overlap",
        "London/NY overlap",
        "New York",
        "New York",
        "Off-hours",
        "Off-hours",
    ]


def test_filter_trades(small):
    kept = filter_trades(small, start=date(2026, 1, 6), end=date(2026, 1, 9))
    assert [t.id for t in kept] == ["3", "4", "5"]
    assert compute_report(kept).net_pnl == 250
    assert len(filter_trades(small, symbols=["eurusd"])) == 3
    # 2026-01-09 19:00 UTC is 2026-01-10 in Kolkata, so it falls outside --to 2026-01-09.
    kolkata = filter_trades(small, end=date(2026, 1, 9), tz=ZoneInfo("Asia/Kolkata"))
    assert [t.id for t in kolkata] == ["1", "2", "3", "4"]


def test_empty_report():
    rep = compute_report([])
    assert rep.trades == 0 and rep.win_rate is None and rep.expectancy is None
    assert rep.equity_curve == [] and rep.max_drawdown.amount == 0
