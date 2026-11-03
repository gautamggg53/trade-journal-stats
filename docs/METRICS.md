# Metric definitions

Every number `trade-stats` prints is defined here. "P&L" always means the
trade's **net** result in account currency (after commission and swap, as
described per format in the README). Trades are ordered by close time.

| Metric | Definition |
| --- | --- |
| Win / loss / break-even | P&L > 0 / P&L < 0 / P&L = 0 exactly |
| Win rate | wins / all trades (break-evens count in the denominator) |
| Gross profit / loss | sum of winning P&L / sum of losing P&L (negative) |
| Average win / loss | gross profit / wins; gross loss / losses |
| Payoff ratio | average win / \|average loss\| |
| Profit factor | gross profit / \|gross loss\|; `n/a` (JSON `null`) when there are no losses |
| Expectancy | net P&L / trades |
| R multiple | `pnl / risk` when the trade has a money `risk`; otherwise, when entry, exit and stop prices and the side are known, `±(exit − entry) / |entry − stop|` (price-based, ignores costs); otherwise `pnl / --risk-per-trade` if given |
| Expectancy (R) | mean R over the trades that have an R value |
| R distribution | counts in buckets `[-inf,-2)`, `[-2,-1)`, `[-1,0)`, `[0,1)`, `[1,2)`, `[2,3)`, `[3,inf)` |
| Max drawdown | largest fall from a running peak of the **closed-trade** equity curve. The curve starts at `--balance` (or 0) at the first trade's open time and steps at each close. Open-trade (floating) drawdown is not visible in closed-trade exports and is not measured. |
| Drawdown % | drawdown / equity at the peak × 100; only with `--balance` |
| Drawdown duration | from the peak to the first later close at or above the peak, or to the last trade if not recovered (marked "not recovered") |
| Streaks | longest run of consecutive wins / losses by close time; a break-even trade ends a streak. Current streak is + for wins, − for losses |
| Daily returns | days are calendar days in `--tz`, keyed on close time. Every Mon–Fri from the first to the last close date is included (0 if nothing closed) plus any Sat/Sun on which a trade closed. Return = that day's P&L / equity at the start of the day. Needs `--balance`, which is taken as the balance at the start of the (filtered) period. |
| Sharpe | mean(daily) / sample stdev(daily) × √252, risk-free rate 0 |
| Sortino | mean(daily) / √(mean(min(r, 0)²)) × √252, target 0, over all days |
| Sessions | fixed UTC windows on the entry hour: Asia 00–07, London 07–12, London/NY overlap 12–16, New York 16–21, Off-hours 21–24. They ignore daylight saving, so they are rough buckets |
| Weekday / hour | entry time (open time, or close time if the format has none) in `--tz` |
| Monthly table | P&L summed by close month in `--tz` |

Caveats:

- Sharpe and Sortino from a few weeks of trades are very noisy; treat them as
  descriptive, not predictive.
- Sizing changes over time distort money-based stats; R statistics are usually
  the better comparison across periods when risk data is available.
