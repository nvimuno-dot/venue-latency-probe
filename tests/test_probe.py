import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

from vprobe import cli, probe


def quote(name: str, t: int, bid: float, ask: float) -> dict:
    return {"v": name, "s": "BTC", "t": t, "b": bid, "a": ask,
            "bs": 1.0, "as": 1.0, "x": None}


def rec(name: str, quotes: list, status: str = "ok", connect: float = 200.0,
        first: float = 300.0) -> dict:
    return {"venue": name, "symbol": "BTC", "status": status, "error": None,
            "connect_ms": connect, "first_quote_ms": first, "quotes": quotes}


def stream(name: str, n: int = 10, step: int = 100, bid: float = 100.0) -> list:
    return [quote(name, 1000 + i * step, bid, bid + 0.02) for i in range(n)]


class TestAnalyseVenue(unittest.TestCase):
    def test_counts_and_rate(self):
        out = probe.analyse_venue(rec("a", stream("a", 10, 100)))
        self.assertEqual(out["quotes"], 10)
        self.assertAlmostEqual(out["updates_per_s"], 10.0, places=1)
        self.assertEqual(out["median_gap_ms"], 100.0)

    def test_spread(self):
        out = probe.analyse_venue(rec("a", stream("a", 4)))
        self.assertAlmostEqual(out["spread_median_bps"], 1.9998, places=3)
        self.assertAlmostEqual(out["spread_min_bps"], 1.9998, places=3)

    def test_last_quote(self):
        out = probe.analyse_venue(rec("a", stream("a", 3, bid=50.0)))
        self.assertEqual(out["last"]["bid"], 50.0)
        self.assertAlmostEqual(out["last"]["mid"], 50.01)

    def test_empty_venue_keeps_error(self):
        out = probe.analyse_venue(rec("a", [], status="error"))
        out_err = probe.analyse_venue({"venue": "a", "symbol": "BTC", "status": "error",
                                       "error": "WebSocketError: 451", "connect_ms": None,
                                       "first_quote_ms": None, "quotes": []})
        self.assertIsNone(out["updates_per_s"])
        self.assertEqual(out_err["error"], "WebSocketError: 451")

    def test_single_quote_has_no_rate(self):
        out = probe.analyse_venue(rec("a", stream("a", 1)))
        self.assertIsNone(out["updates_per_s"])
        self.assertIsNone(out["median_gap_ms"])
        self.assertEqual(out["quotes"], 1)


class TestDispersion(unittest.TestCase):
    def test_three_books(self):
        results = {
            "a": probe.analyse_venue(rec("a", stream("a", 2, bid=100.00))),
            "b": probe.analyse_venue(rec("b", stream("b", 2, bid=101.00))),
            "c": probe.analyse_venue(rec("c", stream("c", 2, bid=102.00))),
        }
        d = probe.dispersion(results)
        self.assertEqual(d["n"], 3)
        self.assertAlmostEqual(d["legs"]["b"], 0.0, places=3)
        self.assertLess(d["legs"]["a"], 0)
        self.assertGreater(d["legs"]["c"], 0)
        self.assertAlmostEqual(d["range_bps"], 200.0, delta=0.1)

    def test_stale_venue_dropped(self):
        fresh = stream("a", 2)
        old = [quote("b", 0, 101.0, 101.02)]
        results = {
            "a": probe.analyse_venue(rec("a", [quote("a", 10_000, 100.0, 100.02)])),
            "b": probe.analyse_venue(rec("b", old)),
        }
        d = probe.dispersion(results, max_age_ms=3000)
        self.assertEqual(d["n"], 1)
        self.assertNotIn("b", d["legs"])

    def test_no_books(self):
        d = probe.dispersion({})
        self.assertIsNone(d["range_bps"])
        self.assertEqual(d["legs"], {})


class TestSnapshotRoundTrip(unittest.TestCase):
    def test_save_load(self):
        snap = {"tool": "venue-latency-probe", "version": "0.1.0",
                "captured_at": "2026-11-19T00:00:00+00:00",
                "window_s": 1.0, "symbol": "BTC",
                "venues": {"a": rec("a", stream("a", 3))}}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "snap.json")
            probe.save(snap, path)
            back = probe.load(path)
        self.assertEqual(back["symbol"], "BTC")
        self.assertEqual(back["venues"]["a"]["venue"], "a")
        result = probe.analyse(back)
        self.assertEqual(result["venues"]["a"]["quotes"], 3)


class TestReplay(unittest.TestCase):
    def test_replay_prints_table(self):
        snap = {"tool": "venue-latency-probe", "version": "0.1.0",
                "captured_at": "2026-11-19T00:00:00+00:00", "window_s": 1.0,
                "symbol": "BTC", "venues": {"a": rec("a", stream("a", 5))}}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "snap.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(snap, fh)
            buf = StringIO()
            with redirect_stdout(buf):
                code = cli.main(["replay", path])
        self.assertEqual(code, 0)
        out = buf.getvalue()
        self.assertIn("venue-latency-probe", out)
        self.assertIn("median gap", out)

    def test_venues_command(self):
        buf = StringIO()
        with redirect_stdout(buf):
            code = cli.main(["venues"])
        self.assertEqual(code, 0)
        self.assertIn("hyperliquid", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
