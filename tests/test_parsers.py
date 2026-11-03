from datetime import datetime, timedelta, timezone

import pytest

from trade_journal_stats import InputError, compute_report, load_trades
from trade_journal_stats.parsers import detect_format
from trade_journal_stats.parsers.common import (
    decode,
    get_tz,
    parse_datetime,
    parse_number,
    parse_side,
    read_csv_rows,
)

UTC = timezone.utc
SMALL_PNL = [200, -100, -50, 0, 300, -150]


def test_generic(fx):
    h = load_trades(fx / "generic_small.csv")
    assert h.format == "generic"
    assert [t.pnl for t in h.trades] == SMALL_PNL
    t = h.trades[0]
    assert (t.symbol, t.side, t.risk) == ("EURUSD", "long", 100)
    assert t.open_time == datetime(2026, 1, 5, 8, tzinfo=UTC)
    assert h.trades[2].side == "long"  # "buy"
    assert h.trades[3].side == "short"  # "sell"


@pytest.mark.parametrize("name", ["mt5_report.html", "mt5_positions.csv"])
def test_mt5_matches_generic(fx, name):
    h = load_trades(fx / name)
    assert h.format == "mt5"
    assert [t.pnl for t in h.trades] == pytest.approx(SMALL_PNL)
    rs = [t.r_multiple for t in h.trades]
    assert rs == pytest.approx([2, -1, -0.5, 0, 3, -1.5])
    assert h.trades[3].volume == 0.10 and h.trades[3].symbol == "XAUUSD"
    rep = compute_report(h.trades, balance=10_000)
    gen = compute_report(load_trades(fx / "generic_small.csv").trades, balance=10_000)
    assert rep.max_drawdown == gen.max_drawdown
    assert rep.monthly == gen.monthly


def test_mt5_source_tz(fx):
    h = load_trades(fx / "mt5_report.html", source_tz="+02:00")
    assert h.trades[0].close_time.utcoffset() == timedelta(hours=2)
    assert h.trades[0].close_time.astimezone(UTC).hour == 8


def test_mt5_html_without_positions_fails(tmp_path):
    p = tmp_path / "x.html"
    p.write_text("<html><table><tr><td>hello</td></tr></table></html>")
    with pytest.raises(InputError, match="MT5"):
        load_trades(p)
    with pytest.raises(InputError, match="Positions"):
        load_trades(p, fmt="mt5")


def test_ctrader(fx):
    h = load_trades(fx / "ctrader_history.csv")
    assert h.format == "ctrader"
    assert [t.pnl for t in h.trades] == [180, -50, -40]
    t = h.trades[0]
    # header says UTC+2; 12:00:00.5 local -> 10:00:00.5 UTC
    assert t.close_time.astimezone(UTC) == datetime(2026, 1, 5, 10, 0, 0, 500000, tzinfo=UTC)
    assert (t.side, t.volume, t.symbol) == ("long", 1.0, "EURUSD")
    assert h.trades[1].side == "short"
    assert any("UTC+2" in n for n in h.notes)


def test_ctrader_gross_fallback(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text(
        "ID,Symbol,Closing time,Gross USD,Commission,Swap\n1,EURUSD,2026-01-05 10:00,100,-5,-1\n"
    )
    h = load_trades(p, fmt="ctrader")
    assert h.trades[0].pnl == 94
    assert any("Gross" in n for n in h.notes)


def test_ctrader_missing_columns(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("ID,Symbol\n1,EURUSD\n")
    with pytest.raises(InputError, match="Closing time"):
        load_trades(p, fmt="ctrader")
    p.write_text("ID,Closing time\n1,2026-01-01 10:00\n")
    with pytest.raises(InputError, match="Net or Gross"):
        load_trades(p, fmt="ctrader")


@pytest.mark.parametrize("name", ["tradingview_old.csv", "tradingview_new.csv"])
def test_tradingview(fx, name):
    h = load_trades(fx / name, default_symbol="es1!")
    assert h.format == "tradingview"
    assert [t.pnl for t in h.trades] == [500, -250]  # open trade #3 skipped
    t = h.trades[0]
    assert (t.symbol, t.side, t.volume) == ("ES1!", "long", 2)
    assert (t.entry_price, t.exit_price) == (5005, 5010)
    assert t.open_time == datetime(2026, 4, 1, 14, 30, tzinfo=UTC)
    assert h.trades[1].side == "short"


def test_tradingview_open_trade_note(fx):
    h = load_trades(fx / "tradingview_old.csv")
    assert any("skipped 1" in n for n in h.notes)


def test_format_override_and_unknown(fx, tmp_path):
    with pytest.raises(InputError, match="unknown format"):
        load_trades(fx / "generic_small.csv", fmt="xlsx")
    p = tmp_path / "u.csv"
    p.write_text("a,b\n1,2\n")
    with pytest.raises(InputError, match="--format"):
        load_trades(p)
    with pytest.raises(InputError, match="close_time and pnl"):
        load_trades(p, fmt="generic")


def test_missing_and_empty_files(tmp_path):
    with pytest.raises(InputError, match="cannot read"):
        load_trades(tmp_path / "nope.csv")
    (tmp_path / "e.csv").write_text("\n\n")
    with pytest.raises(InputError, match="no rows"):
        load_trades(tmp_path / "e.csv")


def test_semicolon_decimal_comma(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text(
        "close_time;pnl;symbol\n2026-01-05 10:00;1.234,50;dax\n2026-01-06 10:00;-34,50;dax\n",
        encoding="utf-8",
    )
    h = load_trades(p, decimal_comma=True)
    assert [t.pnl for t in h.trades] == [1234.5, -34.5]
    assert h.trades[0].symbol == "DAX"


def test_date_format_override(tmp_path):
    p = tmp_path / "d.csv"
    p.write_text("close_time,pnl\n01/02/2026 10:00,5\n")
    assert load_trades(p).trades[0].close_time.month == 2  # day-first by default
    h = load_trades(p, date_format="%m/%d/%Y %H:%M")
    assert h.trades[0].close_time.month == 1
    with pytest.raises(InputError, match="--date-format"):
        load_trades(p, date_format="%Y")


def test_generic_bad_values(tmp_path):
    p = tmp_path / "b.csv"
    p.write_text("close_time,pnl\n2026-01-05 10:00,abc\n")
    with pytest.raises(InputError, match="pnl on row 2"):
        load_trades(p)
    p.write_text("close_time,pnl\nyesterday,1\n")
    with pytest.raises(InputError, match="close_time on row 2"):
        load_trades(p)


def test_sorted_by_close_time(tmp_path):
    p = tmp_path / "o.csv"
    p.write_text("close_time,pnl\n2026-01-06 10:00,2\n2026-01-05 10:00,1\n")
    assert [t.pnl for t in load_trades(p).trades] == [1, 2]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1 234.50", 1234.5),
        ("-1,234.50", -1234.5),
        ("(12.30)", -12.3),
        ("$5", 5.0),
        ("\u22123", -3.0),
        ("+7", 7.0),
        ("1e3", 1000.0),
    ],
)
def test_parse_number(text, expected):
    assert parse_number(text) == expected


def test_parse_number_errors():
    assert parse_number("", empty=0.0) == 0.0
    with pytest.raises(InputError):
        parse_number("")
    with pytest.raises(InputError):
        parse_number("1.2.3")


def test_parse_datetime_variants():
    tz = get_tz("+05:30")
    assert parse_datetime("2026.01.05 10:00:00", UTC).hour == 10
    assert parse_datetime("2026-01-05T10:00:00Z", tz).utcoffset() == timedelta(0)
    assert parse_datetime("2026-01-05 10:00", tz).utcoffset() == timedelta(hours=5, minutes=30)
    with pytest.raises(InputError):
        parse_datetime("", UTC)


def test_get_tz():
    assert get_tz(None) is UTC
    assert get_tz("GMT") is UTC
    assert get_tz("UTC-3").utcoffset(None) == timedelta(hours=-3)
    assert str(get_tz("Europe/London")) == "Europe/London"
    with pytest.raises(InputError, match="unknown timezone"):
        get_tz("Mars/Olympus")


def test_parse_side():
    assert [parse_side(x) for x in ("Buy", "LONG", "sell", "Short", "", "?")] == [
        "long",
        "long",
        "short",
        "short",
        "",
        "",
    ]


def test_decode_variants():
    assert decode("a,b".encode("utf-16")) == "a,b"
    assert decode(b"\xef\xbb\xbfa,b") == "a,b"
    assert decode("a,b".encode("utf-16-le")) == "a,b"
    assert decode(b"caf\xe9") == "café"  # cp1252 fallback


def test_detect_format_rows():
    assert detect_format(read_csv_rows("Trade #,Type,Date/Time\n"), False) == "tradingview"
    assert detect_format(read_csv_rows("close_time,pnl\n"), False) == "generic"
