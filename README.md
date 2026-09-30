# SKHY Premium Monitor

Live premium monitor for Binance USDⓈ-M Futures.

## Live chart
The `index.html` page connects **directly from the browser to Binance Futures WebSocket** and calculates:

```
PRE = SKHYUSDT / (SKHYNIXUSDT / 10) - 1
```

It uses the Binance mark-price streams for `SKHYUSDT` and `SKHYNIXUSDT`, refreshes live, and stores sampled history locally in the browser every 10 seconds.

## Why browser WebSocket?
GitHub-hosted Actions currently receive HTTP 451 from Binance's REST endpoint because of the runner's network/geographic location. The live page avoids that runner limitation by connecting from the user's own browser directly to Binance.

## Files
- `index.html`: live chart/dashboard
- `premium.py`: REST collector (kept for optional use from an allowed host)
- `history.csv` / `latest.json`: produced when the REST collector runs successfully
