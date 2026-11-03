import json

import pytest

from trade_journal_stats.cli import main


def test_text_output(fx, capsys):
    assert main([str(fx / "generic_small.csv"), "--balance", "10000"]) == 0
    out = capsys.readouterr().out
    assert "Net P&L" in out and "200.00" in out
    assert "Monthly P&L" in out and "By session (UTC)" in out
    assert "R-multiple distribution" in out
    assert "150.00 (1.47%)" in out


def test_json_stdout(fx, capsys):
    assert main([str(fx / "generic_small.csv"), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["net_pnl"] == 200
    assert data["by_symbol"]["EURUSD"]["trades"] == 3
    assert data["profit_factor"] == pytest.approx(5 / 3)


def test_csv_stdout(fx, capsys):
    assert main([str(fx / "generic_small.csv"), "--csv"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "section,group,metric,value"
    assert "summary,,net_pnl,200.0" in out
    assert "monthly,2026,Total,200.0" in out
    assert "by_symbol,EURUSD,net_pnl,450.0" in out


def test_files_and_html(fx, tmp_path, capsys):
    html_p, json_p = tmp_path / "r.html", tmp_path / "r.json"
    rc = main(
        [
            str(fx / "generic_small.csv"),
            "--balance",
            "10000",
            "--html",
            str(html_p),
            "--json",
            str(json_p),
            "--title",
            "Demo <journal>",
        ]
    )
    assert rc == 0
    html = html_p.read_text()
    assert "<svg" in html and "<polyline" in html
    assert "http" not in html.replace('xmlns="http://www.w3.org/2000/svg"', "")
    assert "Demo &lt;journal&gt;" in html
    assert "Not financial advice" in html
    assert json.loads(json_p.read_text())["trades"] == 6
    assert "Trade journal" not in capsys.readouterr().out.splitlines()[0]  # custom title


def test_filters(fx, capsys):
    assert (
        main(
            [str(fx / "generic_small.csv"), "--from", "2026-01-06", "--to", "2026-01-09", "--json"]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["net_pnl"] == 250
    assert main([str(fx / "generic_small.csv"), "--symbol", "GBPUSD", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["net_pnl"] == -250
    assert "6 trade(s)" in data["notes"][0] and "2 after filters" in data["notes"][0]


def test_tz_and_format_flags(fx, capsys):
    assert (
        main(
            [
                str(fx / "tradingview_new.csv"),
                "--format",
                "tradingview",
                "--source-tz",
                "America/New_York",
                "--tz",
                "UTC",
                "--default-symbol",
                "ES",
                "--json",
            ]
        )
        == 0
    )
    data = json.loads(capsys.readouterr().out)
    assert list(data["by_symbol"]) == ["ES"]
    assert data["first_trade"].startswith("2026-04-01T20:00")  # 16:00 EDT -> 20:00 UTC


def test_errors(fx, tmp_path, capsys):
    assert main([str(tmp_path / "missing.csv")]) == 2
    assert "error:" in capsys.readouterr().err
    assert main([str(fx / "generic_small.csv"), "--symbol", "BTCUSD"]) == 1
    assert "no closed trades" in capsys.readouterr().err
    assert main([str(fx / "generic_small.csv"), "--balance", "0"]) == 2
    with pytest.raises(SystemExit):
        main([str(fx / "generic_small.csv"), "--from", "Jan 1"])


def test_single_trade_html(tmp_path):
    p = tmp_path / "one.csv"
    p.write_text("close_time,pnl\n2026-01-05 10:00,5\n")
    out = tmp_path / "one.html"
    assert main([str(p), "--html", str(out)]) == 0
    assert "<svg" in out.read_text()  # start point + one trade = 2 points


def test_module_entry(fx):
    import subprocess
    import sys

    r = subprocess.run(
        [sys.executable, "-m", "trade_journal_stats", "--version"], capture_output=True, text=True
    )
    assert r.returncode == 0 and "0.1.0" in r.stdout
