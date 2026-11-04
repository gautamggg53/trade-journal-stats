# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- CSV files that start with Excel's `sep=;` line (common in semicolon-delimited
  exports from European locales) are now read with that delimiter, and the line
  is no longer mistaken for the header.
- Delimiter sniffing ignores commas inside quoted header cells, so a header like
  `"Profit, USD";"Close time"` is split on `;` rather than `,`.

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
