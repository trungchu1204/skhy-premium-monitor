# SKHY Premium Monitor

This repository automatically fetches Binance USDⓈ-M Futures **mark prices** for `SKHYUSDT` and `SKHYNIXUSDT` every hour and calculates:

```
PRE = SKHYUSDT / (SKHYNIXUSDT / 10) - 1
```

Outputs:
- `latest.json`: latest synchronized snapshot
- `history.csv`: hourly history

Data source: Binance public futures market-data endpoint `/fapi/v1/premiumIndex`.

No Binance API key is required.
