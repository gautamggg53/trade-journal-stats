# Test fixtures

Every file here is **synthetic**: hand-written for tests, not exported from a
real account. Trades, prices, IDs and balances are made up.

- `generic_small.csv`: 6 trades whose statistics are hand-computed in
  `tests/test_stats.py`.
- `generic_stops.csv`: R from stop prices instead of a risk column.
- `mt5_report.html`: a minimal MT5-style "Trade History Report" (UTF-16) built
  from public descriptions of the layout, with the same 6 trades.
- `mt5_positions.csv`: the MT5 Positions table saved as CSV.
- `ctrader_history.csv`: cTrader History-tab style CSV (header timezone UTC+2,
  `Net EUR`).
- `tradingview_old.csv` / `tradingview_new.csv`: TradingView List of Trades
  with the older (`Trade #`, `Profit USD`) and newer (`Trade number`,
  `Net P&L USD`) header spellings.
