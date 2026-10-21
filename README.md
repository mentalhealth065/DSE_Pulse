# DSE Pulse 📈

A free, mobile-and-laptop-friendly **Dhaka Stock Exchange** dashboard that runs on GitHub Pages.

- **Market overview**: DSEX / DS30 / DSES, advancers vs decliners, top gainers and losers, most traded, sector heat
- **Screener**: search, sort and filter every stock by sector or signal
- **Stock page**: candlestick/line chart with SMA 20/50/200, Bollinger bands, volume, RSI, MACD and a crosshair
- **Buy / Hold / Sell signals** from six technical checks, with a plain-English "why", key levels, and a **back-test** that shows whether the signals worked on that stock's own history
- **Watchlist & portfolio** with profit/loss and a signal-based hint for each holding (saved only in your browser)
- Light / dark theme, works as a phone app (Add to Home Screen)

> ⚠️ **Not investment advice.** Signals are mechanical rules applied to past prices. They don't know about company news, dividends, record dates or circuit-breaker limits. Check prices on the official DSE site or with your broker before trading.

Out of the box the app shows **generated demo data** (a yellow banner says so). Follow Part 2 to connect real DSE data.

---

## Part 1: Publish the website (about 5 minutes)

1. **Create a GitHub account** at <https://github.com/signup> (skip if you have one).
2. Click **+ → New repository** (top right).
   - Repository name: `dse-pulse`
   - Choose **Public**
   - Tick **Add a README file**? No. Leave it **unticked**.
   - Click **Create repository**.
3. **Upload the files.** On the empty repository page click **uploading an existing file**, then drag in **everything from the unzipped `dse-pulse` folder** (`index.html`, `README.md`, `scripts/`, `data/`, `src/`, `build.py`, `test/`, `.nojekyll`). Click **Commit changes**.
4. **Add the workflow file** (hidden folders like `.github` are often skipped by drag-and-drop):
   - Click **Add file → Create new file**.
   - In the name box type exactly: `.github/workflows/update-data.yml` (typing `/` creates the folders).
   - Open `update-data.yml` from the zip in a text editor, copy everything, paste it in, and click **Commit changes**.
5. **Turn on GitHub Pages:** **Settings → Pages → Build and deployment → Source: Deploy from a branch → Branch: `main` / `(root)` → Save.**
6. Wait about a minute, then open **`https://YOUR-USERNAME.github.io/dse-pulse/`**. That's your app. ✅

### Prefer the command line?

```bash
cd dse-pulse
git init -b main
git add .
git commit -m "DSE Pulse"
git remote add origin https://github.com/YOUR-USERNAME/dse-pulse.git
git push -u origin main
```

---

## Part 2: Connect real DSE data (about 5 minutes)

A website on GitHub Pages cannot read dsebd.org directly (browsers block it), so a small robot (GitHub Action) fetches the data on a schedule and saves it as JSON files in your repo. The website reads those files.

1. **Allow the robot to save files:** **Settings → Actions → General → Workflow permissions → select "Read and write permissions" → Save.**
2. **Build the history (once):** open the **Actions** tab → **Update DSE data** → **Run workflow** → keep `mode = backfill` and `days = 400` → **Run workflow**. This can take 10–30 minutes. When it turns green, `data/market.json` appears in your repo.
3. Reload your site. The yellow demo banner disappears and the header shows **Open / Closed · as of <date>**.

After that it updates itself:

| When (Dhaka time) | What happens |
|---|---|
| Sun–Thu, every 30 min during 10:00–14:30 | `data/live.json` is refreshed (latest prices) |
| Sun–Thu, 15:10 | today's closing bar is added to `data/market.json` (signals recalculate) |

You can also run it by hand any time: **Actions → Update DSE data → Run workflow**.

### If the backfill fails or returns no data

dsebd.org sometimes blocks cloud servers. Run the fetcher on your own computer instead (works best from Bangladesh):

```bash
pip install bdshare pandas lxml
python scripts/fetch_dse.py --mode backfill --days 400
git add data && git commit -m "data" && git push
```

Repeat `python scripts/fetch_dse.py --mode close` after each market close if you prefer to update manually.

Notes
- GitHub pauses scheduled workflows after ~60 days with no repository activity. If updates stop, open the Actions tab and click **Enable workflow**.
- The fetcher uses the open-source [`bdshare`](https://pypi.org/project/bdshare/) library, which reads public pages of dsebd.org. Check DSE's terms of use for your intended use.
- DSE's price page doesn't list the day's open, so the closing bar uses the previous close as the open. Daily candles are therefore approximate; indicators use closes, highs, lows and volume.

---

## How the signals work

Each stock is scored from **−100 to +100**:

| Check | Max points | Looks at |
|---|---|---|
| Trend | ±30 | price vs 50-day and 200-day averages; 20-day vs 50-day |
| MACD | ±20 | MACD vs signal line, rising/fading momentum, fresh crossovers |
| RSI (14) | ±15 | below 30 oversold (+), 55–70 healthy (+), above 70 overbought (−) |
| Bollinger | ±10 | price stretched to lower band (+) or upper band (−) |
| Volume | ±10 | heavy volume on an up day (+) or down day (−) |
| Momentum | ±10 | 3-month return, position in 52-week range |

**≥ +55** Strong Buy · **≥ +25** Buy · **−25 … +25** Hold · **≤ −25** Sell · **≤ −55** Strong Sell. Stocks with under 30 days of history get no signal. Stocks averaging under ৳10 lakh of turnover a day are tagged **thin** and left out of "top picks".

The **back-test** replays the rules over history and reports what happened 10 trading days after each *new* Buy/Sell signal versus a random day. If Buy signals don't beat the random-day average for a stock, don't lean on them for that stock.

---

## Customising

- `index.html` is the finished app: edit it directly, or edit `src/*` and run `python3 build.py` to regenerate it.
- Company names and sectors are in `const META` in `src/data.js`. Symbols not listed still work and show under "Other".
- Signal weights and thresholds are in `src/ind.js` (`scoreAt` and `TH`).
- Check the engine: `node test/engine.test.js`.

## Files

```
index.html                       the app (single file, no build needed)
data/market.json, live.json      written by the robot
scripts/fetch_dse.py             downloads DSE data
.github/workflows/update-data.yml  schedule for the robot
src/, build.py, test/            source, optional
```
