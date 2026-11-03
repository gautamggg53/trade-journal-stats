"""Generate examples/sample_trades.csv: SYNTHETIC trades for demos (seeded, reproducible).

Nothing here comes from a real account. Run: python examples/make_sample.py
"""

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

SYMBOLS = {"EURUSD": 0.38, "GBPUSD": 0.34, "XAUUSD": 0.4, "US500": 0.36}


def main() -> None:
    rng = random.Random(42)
    day = datetime(2026, 1, 5)
    rows = []
    n = 0
    while day < datetime(2026, 6, 30):
        if day.weekday() < 5:
            for _ in range(rng.choice([0, 1, 1, 2])):
                n += 1
                sym = rng.choice(list(SYMBOLS))
                opened = day + timedelta(hours=rng.randint(1, 19), minutes=rng.choice([0, 15, 30]))
                closed = opened + timedelta(minutes=rng.randint(10, 300))
                risk = 100.0
                if rng.random() < SYMBOLS[sym]:
                    r = rng.choice([1.0, 1.5, 2.0, 2.0, 3.0]) * rng.uniform(0.8, 1.0)
                else:
                    r = -rng.uniform(0.5, 1.05)
                rows.append(
                    [
                        n,
                        sym,
                        rng.choice(["long", "short"]),
                        opened.strftime("%Y-%m-%d %H:%M"),
                        closed.strftime("%Y-%m-%d %H:%M"),
                        f"{r * risk:.2f}",
                        f"{risk:.2f}",
                    ]
                )
        day += timedelta(days=1)
    out = Path(__file__).with_name("sample_trades.csv")
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "symbol", "side", "open_time", "close_time", "pnl", "risk"])
        w.writerows(rows)
    print(f"wrote {len(rows)} synthetic trades to {out}")


if __name__ == "__main__":
    main()
