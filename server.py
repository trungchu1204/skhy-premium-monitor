import os
import sqlite3
import threading
import time
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, request, send_from_directory

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "premium.db")
POLL_SECONDS = int(os.environ.get("POLL_SECONDS", "300"))

BINANCE_URLS = [
    "https://fapi.binance.com/fapi/v1/premiumIndex",
    "https://fapi1.binance.com/fapi/v1/premiumIndex",
    "https://fapi2.binance.com/fapi/v1/premiumIndex",
    "https://fapi3.binance.com/fapi/v1/premiumIndex",
    "https://fapi4.binance.com/fapi/v1/premiumIndex",
]

app = Flask(__name__, static_folder="web")

def db():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS premium_history (
            ts_ms INTEGER PRIMARY KEY,
            timestamp_utc TEXT NOT NULL,
            skhy REAL NOT NULL,
            skhynix REAL NOT NULL,
            premium_pct REAL NOT NULL,
            source_url TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn

def fetch_prices():
    last_error = None
    headers = {"User-Agent": "skhy-premium-monitor/1.0"}
    for url in BINANCE_URLS:
        try:
            r = requests.get(url, timeout=15, headers=headers)
            r.raise_for_status()
            rows = r.json()
            if not isinstance(rows, list):
                rows = [rows]
            by_symbol = {x.get("symbol"): x for x in rows}
            a = by_symbol.get("SKHYUSDT")
            b = by_symbol.get("SKHYNIXUSDT")
            if not a or not b:
                raise RuntimeError("Missing SKHYUSDT or SKHYNIXUSDT in Binance response")
            skhy = float(a["markPrice"])
            skhynix = float(b["markPrice"])
            ts_ms = max(int(a["time"]), int(b["time"]))
            premium_pct = (skhy / (skhynix / 10.0) - 1.0) * 100.0
            return {
                "ts_ms": ts_ms,
                "timestamp_utc": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat(),
                "skhy": skhy,
                "skhynix": skhynix,
                "premium_pct": premium_pct,
                "source_url": url,
            }
        except Exception as e:
            last_error = f"{url}: {e}"
    raise RuntimeError(last_error or "Unable to fetch Binance data")

def save_point(p):
    conn = db()
    try:
        conn.execute(
            """INSERT OR REPLACE INTO premium_history
               (ts_ms, timestamp_utc, skhy, skhynix, premium_pct, source_url)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (p["ts_ms"], p["timestamp_utc"], p["skhy"], p["skhynix"], p["premium_pct"], p["source_url"])
        )
        # Keep 90 days of 5-minute data.
        cutoff = int(time.time() * 1000) - 90 * 86400 * 1000
        conn.execute("DELETE FROM premium_history WHERE ts_ms < ?", (cutoff,))
        conn.commit()
    finally:
        conn.close()

collector_state = {"last_ok": None, "last_error": None}

def collector():
    # Run immediately, then every POLL_SECONDS.
    while True:
        try:
            p = fetch_prices()
            save_point(p)
            collector_state["last_ok"] = p
            collector_state["last_error"] = None
            print(f"[OK] {p['timestamp_utc']} PRE={p['premium_pct']:.4f}%")
        except Exception as e:
            collector_state["last_error"] = str(e)
            print(f"[ERROR] {e}")
        time.sleep(POLL_SECONDS)

@app.get("/")
def index():
    return send_from_directory("web", "index.html")

@app.get("/api/latest")
def latest():
    conn = db()
    try:
        row = conn.execute(
            "SELECT ts_ms,timestamp_utc,skhy,skhynix,premium_pct,source_url FROM premium_history ORDER BY ts_ms DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return jsonify({"ok": False, "error": collector_state["last_error"] or "No data yet"}), 503
    return jsonify({
        "ok": True,
        "ts_ms": row[0],
        "timestamp_utc": row[1],
        "skhy": row[2],
        "skhynix": row[3],
        "premium_pct": row[4],
        "source_url": row[5],
        "collector_error": collector_state["last_error"],
    })

@app.get("/api/history")
def history():
    hours = request.args.get("hours", "24")
    try:
        hours = max(1, min(24 * 90, int(hours)))
    except ValueError:
        hours = 24
    cutoff = int(time.time() * 1000) - hours * 3600 * 1000
    conn = db()
    try:
        rows = conn.execute(
            """SELECT ts_ms,timestamp_utc,skhy,skhynix,premium_pct
               FROM premium_history WHERE ts_ms >= ? ORDER BY ts_ms ASC""",
            (cutoff,)
        ).fetchall()
    finally:
        conn.close()
    return jsonify({
        "ok": True,
        "hours": hours,
        "count": len(rows),
        "data": [
            {"ts_ms": r[0], "timestamp_utc": r[1], "skhy": r[2], "skhynix": r[3], "premium_pct": r[4]}
            for r in rows
        ],
    })

@app.get("/health")
def health():
    return jsonify({"ok": True, "last_error": collector_state["last_error"]})

if __name__ == "__main__":
    db().close()
    t = threading.Thread(target=collector, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), threaded=True)
