# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- A lone comma that can't be thousands grouping (`12,50`, `1,5`, `0,125`) is now
  read as a decimal comma even without `--decimal-comma`, so European P&L values
  are no longer inflated 10x to 1000x; with the flag, `0.125` and `1.5` likewise
  stay decimals. `1,234` is still ambiguous and follows the flag.
- CSV files that start with Excel's `sep=;` line (common in semicolon-delimited
  exports from European locales) are now read with that delimiter, and the line
  is no longer mistaken for the header.
- Delimiter sniffing ignores commas inside quoted header cells, so a header like
  `"Profit, USD";"Close time"` is split on `;` rather than `,`.
- A number that contains both `.` and `,` is read using the rightmost mark as
  the decimal point. Before, `1.234,50` without `--decimal-comma` was silently
  read as `1.2345` (and `1,234.50` with the flag likewise), which skewed P&L.
- Overflowing values such as `1e400` are rejected with a clear error instead of
  becoming infinity and breaking every statistic.

## [0.1.0] - 2026-11-03

### Added

- `trade-stats` CLI and `trade_journal_stats` library.
- Input formats: documented generic CSV, MT5 Trade History Report (HTML or its
  Positions table as CSV), cTrader History CSV, TradingView List of Trades CSV.
  Auto-detection with a `--format` override.
- Statistics: net P&L, win rate, average win/loss, payoff ratio, profit factor,
  expectancy (money and R), R-multiple distribution, max closed-equity drawdown
  with duration, win/loss streaks, Sharpe and Sortino on daily returns.
- Breakdowns by symbol, side, session, weekday and hour, and a monthly P&L table.
- Output as a terminal table, JSON, long-format CSV, and a self-contained HTML
  report with an inline SVG equity curve.
- Filters: `--from`, `--to`, `--symbol`; timezones: `--source-tz`, `--tz`.
