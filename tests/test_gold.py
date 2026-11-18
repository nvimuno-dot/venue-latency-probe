import unittest

from vprobe import gold


def leg_record(key: str, bid: float, ask: float, t: int = 1000,
               status: str = "ok") -> dict:
    venue = gold.LEG_BY_KEY[key]["venue"]
    symbol = gold.LEG_BY_KEY[key]["symbol"]
    return {"venue": venue, "symbol": symbol, "status": status, "error": None,
            "connect_ms": 200.0, "first_quote_ms": 300.0,
            "quotes": [{"v": venue, "s": symbol, "t": t, "b": bid, "a": ask,
                        "bs": 1.0, "as": 1.0, "x": None}]}


def snapshot(**legs) -> dict:
    return {"window_s": 8.0, "legs": legs}


class TestPremium(unittest.TestCase):
    def test_anchor_has_zero_premium(self):
        result = gold.analyse(snapshot(okx_paxg_spot=leg_record("okx_paxg_spot", 1000.0, 1000.2)))
        self.assertEqual(result["anchor"], "okx_paxg_spot")
        self.assertAlmostEqual(result["legs"]["okx_paxg_spot"]["premium_bps"], 0.0)

    def test_perp_below_spot(self):
        result = gold.analyse(snapshot(
            okx_paxg_spot=leg_record("okx_paxg_spot", 1000.0, 1000.2),
            binance_paxg_perp=leg_record("binance_paxg_perp", 999.5, 999.6),
        ))
        self.assertAlmostEqual(result["legs"]["binance_paxg_perp"]["premium_bps"], -5.5, places=1)

    def test_xaut_premium(self):
        result = gold.analyse(snapshot(
            okx_paxg_spot=leg_record("okx_paxg_spot", 1000.0, 1000.0),
            okx_xaut_spot=leg_record("okx_xaut_spot", 1001.0, 1001.0),
        ))
        self.assertAlmostEqual(result["legs"]["okx_xaut_spot"]["premium_bps"], 10.0, places=2)

    def test_anchor_falls_back_when_spot_missing(self):
        result = gold.analyse(snapshot(
            okx_paxg_spot={"venue": "okx_spot", "symbol": "PAXG", "status": "error",
                           "error": "WebSocketError: handshake refused", "connect_ms": None,
                           "first_quote_ms": None, "quotes": []},
            hyperliquid_paxg=leg_record("hyperliquid_paxg", 3000.0, 3000.2),
        ))
        self.assertEqual(result["anchor"], "hyperliquid_paxg")
        self.assertAlmostEqual(result["legs"]["hyperliquid_paxg"]["premium_bps"], 0.0)

    def test_stale_leg_is_marked(self):
        result = gold.analyse(snapshot(
            okx_paxg_spot=leg_record("okx_paxg_spot", 1000.0, 1000.2, t=100_000),
            okx_xaut_spot=leg_record("okx_xaut_spot", 1001.0, 1001.2, t=1_000),
        ))
        self.assertEqual(result["legs"]["okx_xaut_spot"]["status"], "stale")
        self.assertGreater(result["legs"]["okx_xaut_spot"]["age_ms"], 3000)

    def test_pairs(self):
        result = gold.analyse(snapshot(
            okx_paxg_spot=leg_record("okx_paxg_spot", 1000.0, 1000.0),
            hyperliquid_paxg=leg_record("hyperliquid_paxg", 999.0, 999.0),
            binance_paxg_perp=leg_record("binance_paxg_perp", 999.5, 999.5),
        ))
        pairs = result["pairs_bps"]
        self.assertIn("HL perp vs spot", pairs)
        self.assertIn("HL perp vs Binance perp", pairs)
        self.assertAlmostEqual(pairs["HL perp vs Binance perp"], -5.0, places=2)

    def test_empty(self):
        result = gold.analyse({"legs": {}})
        self.assertIsNone(result["anchor"])
        self.assertEqual(result["legs"], {})

    def test_spread_uses_quoted_book(self):
        result = gold.analyse(snapshot(
            okx_paxg_spot=leg_record("okx_paxg_spot", 1000.0, 1001.0),
        ))
        # 1.0 wide on a 1000.5 mid -> 9.995 bps
        self.assertAlmostEqual(result["legs"]["okx_paxg_spot"]["spread_bps"], 10.0, places=2)


class TestLegTable(unittest.TestCase):
    def test_every_leg_has_a_venue_and_symbol(self):
        for leg in gold.LEGS:
            self.assertIn(leg["venue"], ("okx_spot", "binance_futures", "hyperliquid"))
            self.assertTrue(leg["symbol"])
            self.assertTrue(leg["label"])

    def test_exactly_one_anchor(self):
        self.assertEqual(sum(1 for leg in gold.LEGS if leg.get("anchor")), 1)


if __name__ == "__main__":
    unittest.main()
