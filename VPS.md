# VPS deployment

This repo includes a small 24/7 server that:
- fetches Binance USDⓈ-M Futures mark prices every 5 minutes,
- calculates `PRE = SKHY / (SKHYNIX / 10) - 1`,
- stores shared history in SQLite,
- serves a dashboard and API from the VPS.

## Recommended VPS location
Use a location where Binance Futures market-data endpoints are reachable. Singapore is a practical first choice. Avoid US-hosted runners because Binance returned HTTP 451 in the GitHub Actions test.

## One-command deployment on Ubuntu
```bash
git clone https://github.com/trungchu1204/skhy-premium-monitor.git
cd skhy-premium-monitor
chmod +x install-vps.sh
./install-vps.sh
```

Then open:
```
http://YOUR_VPS_IP:8080
```

Useful API endpoints:
- `/api/latest`
- `/api/history?hours=24`
- `/health`

Data is stored at `data/premium.db` and persists across container restarts.
