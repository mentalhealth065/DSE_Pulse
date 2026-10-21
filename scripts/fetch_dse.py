#!/usr/bin/env python3
"""
Fetch Dhaka Stock Exchange data with the open-source `bdshare` library and write
JSON files that index.html reads.

  python scripts/fetch_dse.py --mode backfill --days 400   # first run: build history
  python scripts/fetch_dse.py --mode close                 # after market close: append today's bar
  python scripts/fetch_dse.py --mode live                  # intraday snapshot -> data/live.json

Outputs
  data/market.json  history: {dates:[...], stocks:{SYM:{o,h,l,c,v}}, indices:{DSEX:[...]}}
  data/live.json    latest intraday prices (small file)
"""
import argparse, datetime as dt, json, math, os, sys, time
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, os.environ.get("DSE_DATA_DIR", "data"))
MARKET = os.path.join(DATA, "market.json")
LIVE = os.path.join(DATA, "live.json")
DHAKA = ZoneInfo("Asia/Dhaka")
KEEP_DAYS = 520            # trading days kept in market.json (~2 years)
FIELDS = ("o", "h", "l", "c", "v")


def log(*a):
    print(*a, flush=True)


def num(x):
    """'1,234.50' / '-' / NaN -> float or None"""
    if x is None:
        return None
    try:
        if isinstance(x, str):
            x = x.replace(",", "").strip()
            if x in ("", "-", "--", "n/a", "N/A"):
                return None
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def retry(fn, *args, tries=3, wait=6, **kw):
    last = None
    for i in range(tries):
        try:
            return fn(*args, **kw)
        except Exception as e:  # noqa: BLE001 - network scraping, want to retry on anything
            last = e
            log(f"  attempt {i + 1}/{tries} failed: {e}")
            time.sleep(wait * (i + 1))
    raise last


def bd():
    try:
        import bdshare  # type: ignore
    except ImportError:
        sys.exit("bdshare is not installed. Run:  pip install bdshare pandas lxml")
    return bdshare


def col(df, *names):
    """Return the first matching column name (case-insensitive) or None."""
    low = {str(c).strip().lower(): c for c in df.columns}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    for n in names:
        for k, c in low.items():
            if n.lower() in k:
                return c
    return None


# ---------------------------------------------------------------- storage
def load_market():
    if os.path.exists(MARKET):
        with open(MARKET, encoding="utf-8") as f:
            m = json.load(f)
        if m.get("dates"):
            return m
    return {"version": 1, "dates": [], "stocks": {}, "indices": {}}


def ensure_date(m, d):
    """Insert date d (YYYY-MM-DD) keeping order; return its index."""
    if d in m["dates"]:
        return m["dates"].index(d)
    m["dates"].append(d)
    m["dates"].sort()
    i = m["dates"].index(d)
    for s in m["stocks"].values():
        for f in FIELDS:
            s[f].insert(i, None)
    for k in m["indices"]:
        m["indices"][k].insert(i, None)
    return i


def stock(m, sym):
    if sym not in m["stocks"]:
        n = len(m["dates"])
        m["stocks"][sym] = {f: [None] * n for f in FIELDS}
    return m["stocks"][sym]


def put_bar(m, sym, d, o, h, l, c, v):
    if not c or c <= 0:
        return
    i = ensure_date(m, d)
    s = stock(m, sym)
    s["o"][i], s["h"][i], s["l"][i], s["c"][i], s["v"][i] = o or c, h or c, l or c, c, v or 0


def put_index(m, name, d, val):
    if val is None or val <= 0:
        return
    i = ensure_date(m, d)
    if name not in m["indices"]:
        m["indices"][name] = [None] * len(m["dates"])
    m["indices"][name][i] = val


def trim_and_save(m):
    if len(m["dates"]) > KEEP_DAYS:
        cut = len(m["dates"]) - KEEP_DAYS
        m["dates"] = m["dates"][cut:]
        for s in m["stocks"].values():
            for f in FIELDS:
                s[f] = s[f][cut:]
        for k in m["indices"]:
            m["indices"][k] = m["indices"][k][cut:]
    # drop symbols with no data left
    m["stocks"] = {k: v for k, v in m["stocks"].items() if any(x for x in v["c"])}
    m["updated"] = dt.datetime.now(DHAKA).isoformat(timespec="seconds")
    m["source"] = "dsebd.org via bdshare"
    os.makedirs(DATA, exist_ok=True)
    with open(MARKET, "w", encoding="utf-8") as f:
        json.dump(m, f, separators=(",", ":"))
    log(f"saved {MARKET}: {len(m['dates'])} days, {len(m['stocks'])} symbols, indices {list(m['indices'])}")


# ---------------------------------------------------------------- fetchers
def current_prices():
    """Latest prices for every instrument -> list of dict."""
    b = bd()
    df = retry(b.get_current_trade_data)
    if df is None or len(df) == 0:
        raise RuntimeError("DSE returned no current price rows")
    cs = {k: col(df, k) for k in ("symbol", "ltp", "high", "low", "close", "ycp", "volume")}
    if not cs["symbol"] or not cs["ltp"]:
        raise RuntimeError(f"unexpected columns: {list(df.columns)}")
    out = []
    for _, r in df.iterrows():
        sym = str(r[cs["symbol"]]).strip().upper()
        ltp = num(r[cs["ltp"]]) or (num(r[cs["close"]]) if cs["close"] else None)
        ycp = num(r[cs["ycp"]]) if cs["ycp"] else None
        if not sym or not ltp or ltp <= 0:
            continue
        out.append({
            "sym": sym, "ltp": ltp, "ycp": ycp,
            "high": num(r[cs["high"]]) if cs["high"] else None,
            "low": num(r[cs["low"]]) if cs["low"] else None,
            "volume": num(r[cs["volume"]]) if cs["volume"] else 0,
        })
    return out


def market_info(start=None, end=None):
    """Index history rows -> list of (date, {DSEX:..,DS30:..,DSES:..})."""
    b = bd()
    df = None
    try:
        if start and end and hasattr(b, "get_market_info_more_data"):
            df = retry(b.get_market_info_more_data, start, end)
        else:
            df = retry(b.get_market_info)
    except Exception as e:  # noqa: BLE001
        log("  index data unavailable:", e)
        return []
    if df is None or len(df) == 0:
        return []
    df = df.reset_index() if col(df, "date") is None else df
    dcol = col(df, "date")
    cols = {n: col(df, f"{n} index", n) for n in ("DSEX", "DSES", "DS30")}
    rows = []
    for _, r in df.iterrows():
        try:
            d = dt.datetime.strptime(str(r[dcol])[:10], "%Y-%m-%d").date().isoformat()
        except (ValueError, TypeError):
            try:
                d = dt.datetime.strptime(str(r[dcol])[:10], "%d-%m-%Y").date().isoformat()
            except (ValueError, TypeError):
                continue
        rows.append((d, {n: num(r[c]) for n, c in cols.items() if c}))
    return rows


def history_chunk(start, end):
    b = bd()
    fn = getattr(b, "get_hist_data", None) or getattr(b, "get_historical_data", None)
    if fn is None:
        raise RuntimeError("this bdshare version has no historical-data function")
    df = retry(fn, start, end)
    if df is None or len(df) == 0:
        return []
    df = df.reset_index() if col(df, "date") is None else df
    c = {k: col(df, k) for k in ("date", "symbol", "open", "high", "low", "close", "ltp", "ycp", "volume")}
    rows = []
    for _, r in df.iterrows():
        try:
            d = dt.datetime.strptime(str(r[c["date"]])[:10], "%Y-%m-%d").date().isoformat()
        except (ValueError, TypeError):
            continue
        close = num(r[c["close"]]) if c["close"] else None
        if not close:
            close = num(r[c["ltp"]]) if c["ltp"] else None
        ycp = num(r[c["ycp"]]) if c["ycp"] else None
        op = num(r[c["open"]]) if c["open"] else None
        rows.append((d, str(r[c["symbol"]]).strip().upper(), op or ycp, num(r[c["high"]]) if c["high"] else None,
                     num(r[c["low"]]) if c["low"] else None, close, num(r[c["volume"]]) if c["volume"] else 0))
    return rows


# ---------------------------------------------------------------- modes
def trading_today():
    now = dt.datetime.now(DHAKA)
    return now.date().isoformat(), now.weekday() in (4, 5)   # Fri=4, Sat=5 are weekend in Bangladesh


def mode_backfill(days):
    m = load_market()
    end = dt.datetime.now(DHAKA).date()
    start = end - dt.timedelta(days=days)
    cur = start
    log(f"backfilling {start} -> {end}")
    while cur <= end:
        nxt = min(cur + dt.timedelta(days=30), end)
        log(f"  {cur} .. {nxt}")
        try:
            for d, sym, o, h, l, c, v in history_chunk(cur.isoformat(), nxt.isoformat()):
                put_bar(m, sym, d, o, h, l, c, v)
        except Exception as e:  # noqa: BLE001
            log(f"  chunk failed, continuing: {e}")
        cur = nxt + dt.timedelta(days=1)
        time.sleep(1.5)
    try:
        for d, vals in market_info(start.isoformat(), end.isoformat()):
            for k, v in vals.items():
                put_index(m, k, d, v)
    except Exception as e:  # noqa: BLE001
        log("  index backfill failed:", e)
    if not m["stocks"]:
        sys.exit("No data was fetched. dsebd.org may be blocking this server; see README troubleshooting.")
    trim_and_save(m)


def mode_close():
    today, weekend = trading_today()
    if weekend:
        log("Weekend in Bangladesh, nothing to do.")
        return
    m = load_market()
    prices = current_prices()
    # holiday / stale guard: if today's volumes equal the last stored bar's volumes, DSE was closed.
    if m["dates"]:
        last = len(m["dates"]) - 1
        same = tot = 0
        for p in prices:
            s = m["stocks"].get(p["sym"])
            if s and s["v"][last] is not None:
                tot += 1
                same += int(abs((p["volume"] or 0) - s["v"][last]) < 1 and abs(p["ltp"] - (s["c"][last] or 0)) < 1e-9)
        if tot and same / tot > 0.9 and m["dates"][last] != today:
            log("Prices identical to the previous trading day: market was closed today. Skipping.")
            return
    for p in prices:
        put_bar(m, p["sym"], today, p["ycp"], p["high"], p["low"], p["ltp"], p["volume"])
    for d, vals in market_info():
        for k, v in vals.items():
            put_index(m, k, d, v)
    trim_and_save(m)


def mode_live():
    today, weekend = trading_today()
    if weekend:
        log("Weekend in Bangladesh, nothing to do.")
        return
    prices = current_prices()
    idx = {}
    rows = market_info()
    if rows:
        d, vals = sorted(rows)[-1]
        if d == today:
            idx = {k: v for k, v in vals.items() if v}
    snap = {
        "updated": dt.datetime.now(DHAKA).isoformat(timespec="seconds"), "date": today,
        "stocks": {p["sym"]: {"ltp": p["ltp"], "ycp": p["ycp"], "high": p["high"], "low": p["low"], "volume": p["volume"]} for p in prices},
        "indices": idx,
    }
    os.makedirs(DATA, exist_ok=True)
    with open(LIVE, "w", encoding="utf-8") as f:
        json.dump(snap, f, separators=(",", ":"))
    log(f"saved {LIVE}: {len(prices)} symbols")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["backfill", "close", "live"], default="close")
    ap.add_argument("--days", type=int, default=400, help="calendar days to backfill")
    a = ap.parse_args()
    {"backfill": lambda: mode_backfill(a.days), "close": mode_close, "live": mode_live}[a.mode]()
