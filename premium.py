import csv
import json
import os
from datetime import datetime, timezone

import requests

BASE_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
SYMBOLS = {"SKHYUSDT", "SKHYNIXUSDT"}

def get_mark_prices():
    r = requests.get(BASE_URL, timeout=15)
    r.raise_for_status()
    data = r.json()
    prices = {}
    for item in data:
        sym = item.get("symbol")
        if sym in SYMBOLS:
            prices[sym] = {
                "markPrice": float(item["markPrice"]),
                "time": int(item["time"]),
            }
    missing = SYMBOLS - prices.keys()
    if missing:
        raise RuntimeError(f"Missing symbols from Binance response: {sorted(missing)}")
    return prices

def main():
    prices = get_mark_prices()
    skhy = prices["SKHYUSDT"]["markPrice"]
    skhynix = prices["SKHYNIXUSDT"]["markPrice"]
    premium_pct = (skhy / (skhynix / 10.0) - 1.0) * 100.0
    ts_ms = max(prices["SKHYUSDT"]["time"], prices["SKHYNIXUSDT"]["time"])
    ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()

    latest = {
        "timestamp_utc": ts,
        "source": "Binance USDⓈ-M Futures mark price",
        "endpoint": "/fapi/v1/premiumIndex",
        "SKHYUSDT_mark": skhy,
        "SKHYNIXUSDT_mark": skhynix,
        "premium_pct": premium_pct,
        "formula": "SKHYUSDT / (SKHYNIXUSDT / 10) - 1",
    }

    with open("latest.json", "w", encoding="utf-8") as f:
        json.dump(latest, f, ensure_ascii=False, indent=2)

    history_path = "history.csv"
    exists = os.path.exists(history_path)
    with open(history_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["timestamp_utc","SKHYUSDT_mark","SKHYNIXUSDT_mark","premium_pct"])
        w.writerow([ts, f"{skhy:.8f}", f"{skhynix:.8f}", f"{premium_pct:.6f}"])

    print(json.dumps(latest, ensure_ascii=False))

if __name__ == "__main__":
    main()
