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

app = Flask(__name__, static_folder=os.path.join(APP_DIR, "web"))

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
    return send_from_directory(os.path.join(APP_DIR, "web"), "index.html")

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


# Trading UI is intentionally restricted to the VPS browser itself.
# Open it through Remote Desktop at http://127.0.0.1:<PORT>/trade
TRADE_SYMBOLS = {"SKHYUSDT", "SKHYNIXUSDT"}
TRADE_PROXY_ALLOW = {
    ("GET", "/fapi/v1/positionSide/dual"),
    ("GET", "/fapi/v3/positionRisk"),
    ("POST", "/fapi/v1/batchOrders"),
    ("POST", "/fapi/v1/order"),
    ("GET", "/fapi/v1/order"),
    ("DELETE", "/fapi/v1/order"),
}

def _trade_local_only():
    remote = request.remote_addr or ""
    host = (request.host or "").split(":")[0].lower()
    return remote in {"127.0.0.1", "::1"} and host in {"127.0.0.1", "localhost", "::1"}

def _trade_guard():
    if not _trade_local_only():
        return jsonify({
            "ok": False,
            "error": "Trading is local-only. Open http://127.0.0.1:8080/trade inside the VPS."
        }), 403
    return None

@app.get("/trade")
def trade_page():
    denied = _trade_guard()
    if denied:
        return denied
    return send_from_directory(os.path.join(APP_DIR, "web"), "trade.html")

@app.get("/api/trade/market")
def trade_market():
    denied = _trade_guard()
    if denied:
        return denied
    try:
        p = fetch_prices()
        return jsonify({"ok": True, **p})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502

@app.get("/api/trade/time")
def trade_time():
    denied = _trade_guard()
    if denied:
        return denied
    last_error = None
    for base in ["https://fapi.binance.com", "https://fapi1.binance.com", "https://fapi2.binance.com"]:
        try:
            r = requests.get(base + "/fapi/v1/time", timeout=10)
            r.raise_for_status()
            j = r.json()
            return jsonify({"ok": True, "serverTime": int(j["serverTime"])})
        except Exception as e:
            last_error = str(e)
    return jsonify({"ok": False, "error": last_error or "Unable to get Binance server time"}), 502

@app.get("/api/trade/book")
def trade_book():
    denied = _trade_guard()
    if denied:
        return denied
    last_error = None
    for base in ["https://fapi.binance.com", "https://fapi1.binance.com", "https://fapi2.binance.com"]:
        try:
            r = requests.get(base + "/fapi/v1/ticker/bookTicker", timeout=10)
            r.raise_for_status()
            rows = r.json()
            if not isinstance(rows, list):
                rows = [rows]
            by_symbol = {x.get("symbol"): x for x in rows}
            out = {}
            for symbol in TRADE_SYMBOLS:
                x = by_symbol.get(symbol)
                if not x:
                    raise RuntimeError("Missing " + symbol + " in bookTicker")
                out[symbol] = {
                    "bidPrice": x.get("bidPrice"),
                    "bidQty": x.get("bidQty"),
                    "askPrice": x.get("askPrice"),
                    "askQty": x.get("askQty"),
                    "time": x.get("time"),
                }
            return jsonify({"ok": True, "book": out})
        except Exception as e:
            last_error = str(e)
    return jsonify({"ok": False, "error": last_error or "Unable to load bookTicker"}), 502

@app.get("/api/trade/exchange-info")
def trade_exchange_info():
    denied = _trade_guard()
    if denied:
        return denied
    last_error = None
    for base in ["https://fapi.binance.com", "https://fapi1.binance.com", "https://fapi2.binance.com"]:
        try:
            r = requests.get(base + "/fapi/v1/exchangeInfo", timeout=15)
            r.raise_for_status()
            j = r.json()
            symbols = []
            for x in j.get("symbols", []):
                if x.get("symbol") in TRADE_SYMBOLS:
                    symbols.append({
                        "symbol": x.get("symbol"),
                        "status": x.get("status"),
                        "quantityPrecision": x.get("quantityPrecision"),
                        "filters": x.get("filters", []),
                    })
            if len(symbols) != 2:
                raise RuntimeError("Could not find both SKHYUSDT and SKHYNIXUSDT in exchangeInfo")
            return jsonify({"ok": True, "symbols": symbols})
        except Exception as e:
            last_error = str(e)
    return jsonify({"ok": False, "error": last_error or "Unable to load exchangeInfo"}), 502

@app.post("/api/trade/proxy")
def trade_proxy():
    denied = _trade_guard()
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    method = str(body.get("method", "")).upper()
    path = str(body.get("path", ""))
    query = str(body.get("query", ""))
    api_key = str(body.get("api_key", "")).strip()

    if (method, path) not in TRADE_PROXY_ALLOW:
        return jsonify({"ok": False, "error": "This Binance endpoint is not allowed by the trading proxy."}), 400
    if not api_key or len(api_key) > 256:
        return jsonify({"ok": False, "error": "Missing or invalid API key."}), 400
    if not query or len(query) > 20000 or "signature=" not in query:
        return jsonify({"ok": False, "error": "Missing or invalid signed query."}), 400

    # Strictly limit trading to the intended two symbols and simple MARKET / post-only LIMIT orders.
    from urllib.parse import parse_qs
    try:
        q = parse_qs(query, keep_blank_values=True)

        def validate_order(order):
            if order.get("symbol") not in TRADE_SYMBOLS:
                raise ValueError("Unexpected symbol")
            if order.get("side") not in {"BUY", "SELL"}:
                raise ValueError("Invalid side")
            order_type = order.get("type")
            if order_type not in {"MARKET", "LIMIT"}:
                raise ValueError("Only MARKET or LIMIT orders are allowed")
            if order_type == "LIMIT":
                if order.get("timeInForce") != "GTX":
                    raise ValueError("LIMIT orders must use GTX (Post Only)")
                if not order.get("price"):
                    raise ValueError("Post Only LIMIT order requires price")
            if order_type == "MARKET" and order.get("timeInForce"):
                raise ValueError("MARKET order must not include timeInForce")
            if not order.get("quantity"):
                raise ValueError("Quantity is required")
            if order.get("positionSide") not in {None, "BOTH", "LONG", "SHORT"}:
                raise ValueError("Invalid positionSide")

        if method == "POST" and path == "/fapi/v1/batchOrders":
            import json as _json
            raw = q.get("batchOrders", [None])[0]
            orders = _json.loads(raw)
            if not isinstance(orders, list) or not (1 <= len(orders) <= 2):
                raise ValueError("Batch must contain one or two orders")
            for order in orders:
                validate_order(order)

        if path == "/fapi/v1/order":
            symbol = q.get("symbol", [None])[0]
            if symbol not in TRADE_SYMBOLS:
                raise ValueError("Unexpected symbol")
            if method == "POST":
                order = {
                    "symbol": symbol,
                    "side": q.get("side", [None])[0],
                    "type": q.get("type", [None])[0],
                    "timeInForce": q.get("timeInForce", [None])[0],
                    "price": q.get("price", [None])[0],
                    "quantity": q.get("quantity", [None])[0],
                    "positionSide": q.get("positionSide", [None])[0],
                }
                validate_order(order)
            else:
                order_id = q.get("orderId", [None])[0]
                if not order_id or not str(order_id).isdigit():
                    raise ValueError("orderId is required")
    except Exception as e:
        return jsonify({"ok": False, "error": "Rejected trading request: " + str(e)}), 400

    headers = {"X-MBX-APIKEY": api_key, "User-Agent": "skhy-premium-monitor/1.0"}
    last_error = None
    for base in ["https://fapi.binance.com", "https://fapi1.binance.com", "https://fapi2.binance.com"]:
        try:
            url = base + path + "?" + query
            r = requests.request(method, url, headers=headers, timeout=15)
            try:
                payload = r.json()
            except Exception:
                payload = {"raw": r.text}
            return jsonify({"ok": r.ok, "status": r.status_code, "data": payload}), r.status_code
        except Exception as e:
            last_error = str(e)
    return jsonify({"ok": False, "error": last_error or "Unable to reach Binance"}), 502

if __name__ == "__main__":
    db().close()
    t = threading.Thread(target=collector, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), threaded=True)
