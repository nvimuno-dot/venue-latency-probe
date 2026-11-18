"""Collect one short window of public top-of-book from several venues, then
summarise it.

Two clocks matter here and only one is available. Every arrival timestamp is
this machine's wall clock, taken before the JSON is parsed. The venue's own
timestamp is kept next to it but never subtracted from it: the difference
contains the clock offset between two machines that were never synchronised,
which is usually larger than the delay being looked for.

What the summary therefore reports is:

  connect_ms        TCP + TLS + HTTP Upgrade, measured to the end of the
                    handshake. A statement about the path, not about orders.
  first_quote_ms    from the first byte of the connection to the first parsed
                    quote after subscribing. The floor of what this venue can
                    tell you, on this network path, right now.
  updates_per_s     quotes received divided by the observed window. Not the
                    venue's advertised rate.
  median_gap_ms     median time between consecutive quotes, which is the
                    resolution limit for any lead-lag claim about this venue.
  spread_*_bps      quoted spread on each update.

Cross-venue dispersion compares the latest mids of the venues that answered,
in basis points of their median. It is a snapshot of disagreement, not an
arbitrage: the paths between the books, and the fees, are not in the number.
"""

from __future__ import annotations

import gzip
import json
import threading
import time
from datetime import datetime, timezone

from . import stats, venues

DEFAULT_VENUES = ("hyperliquid", "binance_futures", "bybit_linear", "okx_swap")
DEFAULT_SYMBOL = "BTC"
VERSION = "0.1.0"


def _run_venue(venue: venues.Venue, symbol: str, seconds: float) -> dict:
    """Connect, subscribe, and record every quote in the window."""
    rec = {"venue": venue.name, "symbol": symbol, "status": "error", "error": None,
           "connect_ms": None, "first_quote_ms": None, "quotes": []}
    t0 = time.monotonic()
    ws = None
    try:
        ws = venues_ws(venue.url(symbol))
        ws.connect()
        rec["connect_ms"] = round((time.monotonic() - t0) * 1000.0, 1)
        for payload in venue.subscribe(symbol):
            ws.send_text(payload)
        deadline = time.monotonic() + seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            got = ws.recv(timeout=min(1.0, max(0.01, remaining)))
            if got is None:
                continue
            recv_ms = int(time.time() * 1000)
            for quote in venue.parse(got[1].decode("utf-8", "replace"), recv_ms, symbol):
                if rec["first_quote_ms"] is None:
                    rec["first_quote_ms"] = round((time.monotonic() - t0) * 1000.0, 1)
                rec["quotes"].append(quote)
        if rec["quotes"]:
            rec["status"] = "ok"
        else:
            rec["status"] = "timeout"
            rec["error"] = "subscription accepted but no quote arrived"
    except Exception as exc:  # network, TLS, geo-block, protocol
        rec["status"] = "error"
        rec["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if ws is not None:
            ws.close()
    return rec


def venues_ws(url: str):
    """Indirection so tests can substitute a fake socket without patching."""
    from .ws import WebSocket
    return WebSocket(url, connect_timeout=8.0, recv_timeout=1.0)


def capture(venue_names=DEFAULT_VENUES, symbol: str = DEFAULT_SYMBOL,
            seconds: float = 12.0) -> dict:
    """Run all venues in parallel threads so their windows overlap."""
    records: dict[str, dict] = {}
    lock = threading.Lock()

    def work(name: str) -> None:
        venue = venues.build(name)
        rec = _run_venue(venue, symbol, seconds)
        with lock:
            records[name] = rec

    threads = [threading.Thread(target=work, args=(name,), daemon=True)
               for name in venue_names]
    started = datetime.now(timezone.utc)
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=seconds + 20.0)
    return {
        "tool": "venue-latency-probe",
        "version": VERSION,
        "captured_at": started.isoformat(timespec="seconds"),
        "window_s": seconds,
        "symbol": symbol,
        "venues": records,
    }


def analyse_venue(rec: dict) -> dict:
    """Turn one venue's raw quotes into the numbers the table prints."""
    quotes = rec.get("quotes") or []
    out = {
        "venue": rec.get("venue"),
        "symbol": rec.get("symbol"),
        "status": rec.get("status"),
        "error": rec.get("error"),
        "connect_ms": rec.get("connect_ms"),
        "first_quote_ms": rec.get("first_quote_ms"),
        "quotes": len(quotes),
        "updates_per_s": None,
        "median_gap_ms": None,
        "spread_median_bps": None,
        "spread_min_bps": None,
        "last": None,
    }
    # A quote with a crossed or zero book cannot be summarised; drop it and
    # say how many were dropped rather than failing the whole venue.
    valid = []
    for q in quotes:
        if q["b"] <= 0 or q["a"] <= 0 or q["a"] < q["b"]:
            continue
        valid.append(q)
    out["dropped"] = len(quotes) - len(valid)
    quotes = valid
    if not quotes:
        return out
    stamps = [q["t"] for q in quotes]
    span_s = (stamps[-1] - stamps[0]) / 1000.0
    if span_s > 0:
        out["updates_per_s"] = round((len(quotes) - 1) / span_s, 1)
    gap = stats.median_interval_ms(stamps)
    out["median_gap_ms"] = None if gap is None else round(gap, 1)
    spreads = [stats.spread_bps(q["b"], q["a"]) for q in quotes]
    out["spread_median_bps"] = round(stats.median(spreads), 3)
    out["spread_min_bps"] = round(min(spreads), 3)
    last = quotes[-1]
    out["last"] = {"t": last["t"], "bid": last["b"], "ask": last["a"],
                   "mid": stats.mid(last["b"], last["a"]), "x": last.get("x")}
    return out


def dispersion(venue_results: dict[str, dict], max_age_ms: int = 3000) -> dict:
    """Latest mids across venues that answered recently, in bps of the median.

    ``max_age_ms`` drops a venue whose last quote is older than that relative
    to the newest quote in the set, so a stalled feed is not silently averaged
    into the reference.
    """
    fresh = {name: r for name, r in venue_results.items()
             if r.get("status") == "ok" and r.get("last")}
    if not fresh:
        return {"legs": {}, "range_bps": None, "ref_mid": None, "n": 0}
    newest = max(r["last"]["t"] for r in fresh.values())
    fresh = {name: r for name, r in fresh.items()
             if newest - r["last"]["t"] <= max_age_ms}
    if not fresh:
        return {"legs": {}, "range_bps": None, "ref_mid": None, "n": 0}
    mids = [r["last"]["mid"] for r in fresh.values()]
    ref = stats.median(mids)
    legs = {name: round(stats.bps(r["last"]["mid"], ref), 3) for name, r in fresh.items()}
    return {"legs": legs, "range_bps": round(stats.bps(max(mids), min(mids)), 3),
            "ref_mid": ref, "n": len(fresh)}


def analyse(snapshot: dict) -> dict:
    """Full analysis of a capture (live or replayed from disk)."""
    results = {name: analyse_venue(rec)
               for name, rec in (snapshot.get("venues") or {}).items()}
    out = {
        "tool": snapshot.get("tool", "venue-latency-probe"),
        "version": snapshot.get("version", VERSION),
        "captured_at": snapshot.get("captured_at"),
        "window_s": snapshot.get("window_s"),
        "symbol": snapshot.get("symbol"),
        "venues": results,
        "dispersion": dispersion(results),
    }
    if "gold" in snapshot:
        from . import gold
        out["gold"] = gold.analyse(snapshot["gold"])
    return out


def save(snapshot: dict, path: str) -> None:
    """Write a capture. A .gz suffix compresses it; the JSON is repetitive and
    gzip takes roughly 8 to 1 off a one-minute file."""
    if path.endswith(".gz"):
        with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as fh:
            json.dump(snapshot, fh, separators=(",", ":"), sort_keys=True)
        return
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, separators=(",", ":"), sort_keys=True)


def load(path: str) -> dict:
    if path.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
