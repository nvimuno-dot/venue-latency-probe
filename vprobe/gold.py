"""Gold, priced on three rails at once, in one snapshot.

A single ounce of gold has more than one live price. This module takes a
snapshot of the rails that answer on a public socket without an account:

  spot token        PAXG on OKX, redeemable for allocated London gold
  second token      XAUT on OKX, a different issuer and a different trust
  USDT perpetual    PAXGUSDT on Binance USD-M, funded every eight hours
  on-venue perp     PAXG on Hyperliquid, marked by that venue's own oracle

The number printed for each leg is its mid minus the spot anchor's mid, in
basis points. For a token that is an issuer premium. For a perpetual it is the
mark-to-spot basis, which the funding rate is there to charge for.

It does not measure the London-New York bridge: the COMEX contract and the
LBMA lease rate need data that is not on a free public socket, and a delayed
futures print would poison a live cross-venue number. The probe stays inside
what it can timestamp itself.
"""

from __future__ import annotations

import threading

from . import probe, stats

LEGS = (
    {"key": "okx_paxg_spot", "venue": "okx_spot", "symbol": "PAXG",
     "label": "OKX PAXG-USDT", "rail": "spot token (PAXG)", "anchor": True},
    {"key": "okx_xaut_spot", "venue": "okx_spot", "symbol": "XAUT",
     "label": "OKX XAUT-USDT", "rail": "spot token (XAUT)"},
    {"key": "binance_paxg_perp", "venue": "binance_futures", "symbol": "PAXG",
     "label": "Binance PAXGUSDT", "rail": "USDT perpetual"},
    {"key": "hyperliquid_paxg", "venue": "hyperliquid", "symbol": "PAXG",
     "label": "Hyperliquid PAXG", "rail": "perp, venue oracle"},
)

LEG_BY_KEY = {leg["key"]: leg for leg in LEGS}


def capture(seconds: float = 8.0) -> dict:
    """One short window per leg, all connected at once."""
    from . import venues

    records: dict[str, dict] = {}
    lock = threading.Lock()

    def work(leg: dict) -> None:
        venue = venues.build(leg["venue"])
        rec = probe._run_venue(venue, leg["symbol"], seconds)
        with lock:
            records[leg["key"]] = rec

    threads = [threading.Thread(target=work, args=(leg,), daemon=True) for leg in LEGS]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=seconds + 20.0)
    return {"window_s": seconds, "legs": records}


def analyse(snapshot: dict) -> dict:
    """Premium of every leg against the spot anchor, in bps."""
    legs_raw = snapshot.get("legs") or {}
    analysed: dict[str, dict] = {}
    for key, rec in legs_raw.items():
        leg = LEG_BY_KEY.get(key, {"key": key, "label": key, "rail": ""})
        summary = probe.analyse_venue(rec)
        summary["label"] = leg.get("label", key)
        summary["rail"] = leg.get("rail", "")
        analysed[key] = summary

    ok = {k: v for k, v in analysed.items() if v.get("status") == "ok" and v.get("last")}
    newest = max((v["last"]["t"] for v in ok.values()), default=None)
    for v in analysed.values():
        v["age_ms"] = None
        if v.get("last") and newest is not None:
            v["age_ms"] = newest - v["last"]["t"]
            if v["age_ms"] > 3000:
                v["status"] = "stale"

    anchor_key = None
    for leg in LEGS:
        if leg.get("anchor") and leg["key"] in ok:
            anchor_key = leg["key"]
            break
    if anchor_key is None and ok:
        anchor_key = next(iter(ok))
    anchor_mid = analysed[anchor_key]["last"]["mid"] if anchor_key else None

    for v in analysed.values():
        v["premium_bps"] = None
        if anchor_mid and v.get("last"):
            v["premium_bps"] = round(stats.bps(v["last"]["mid"], anchor_mid), 2)
        if v.get("last"):
            v["spread_bps"] = round(stats.spread_bps(v["last"]["bid"], v["last"]["ask"]), 2)

    pairs = {}
    def gap(a: str, b: str, label: str) -> None:
        if a in analysed and b in analysed:
            ma, mb = analysed[a].get("last"), analysed[b].get("last")
            if ma and mb:
                pairs[label] = round(stats.bps(ma["mid"], mb["mid"]), 2)

    gap("okx_xaut_spot", "okx_paxg_spot", "XAUT vs PAXG (issuer, same metal)")
    gap("hyperliquid_paxg", "okx_paxg_spot", "HL perp vs spot")
    gap("binance_paxg_perp", "okx_paxg_spot", "Binance perp vs spot")
    gap("hyperliquid_paxg", "binance_paxg_perp", "HL perp vs Binance perp")

    return {"anchor": anchor_key, "anchor_mid": anchor_mid,
            "window_s": snapshot.get("window_s"), "legs": analysed, "pairs_bps": pairs}
