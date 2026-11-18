import json
import os
import unittest

from vprobe import venues


def load_frames() -> dict:
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "fixtures", "frames.json"), encoding="utf-8") as fh:
        return json.load(fh)


FRAMES = load_frames()


class TestHyperliquid(unittest.TestCase):
    def test_ignores_control_frames(self):
        v = venues.build("hyperliquid")
        self.assertEqual(v.parse(FRAMES["hyperliquid"][0], 1000, "BTC"), [])

    def test_parses_bbo(self):
        v = venues.build("hyperliquid")
        recs = v.parse(FRAMES["hyperliquid"][1], 1234, "BTC")
        self.assertEqual(len(recs), 1)
        q = recs[0]
        self.assertEqual(q["v"], "hyperliquid")
        self.assertEqual(q["s"], "BTC")
        self.assertEqual(q["t"], 1234)
        self.assertEqual(q["b"], 62451.0)
        self.assertEqual(q["a"], 62452.0)
        self.assertLess(q["b"], q["a"])

    def test_drops_other_coin(self):
        v = venues.build("hyperliquid")
        self.assertEqual(v.parse(FRAMES["hyperliquid"][1], 1, "SOL"), [])

    def test_subscription_is_bbo(self):
        v = venues.build("hyperliquid")
        subs = v.subscribe("PAXG")
        self.assertEqual(len(subs), 1)
        self.assertEqual(json.loads(subs[0])["subscription"], {"type": "bbo", "coin": "PAXG"})


class TestBinanceFutures(unittest.TestCase):
    def test_parses_bookticker(self):
        v = venues.build("binance_futures")
        recs = v.parse(FRAMES["binance_futures"][0], 777, "BTC")
        self.assertEqual(len(recs), 1)
        q = recs[0]
        self.assertEqual(q["b"], 62454.0)
        self.assertEqual(q["a"], 62454.1)
        self.assertEqual(q["x"], 1795019268802)

    def test_market_symbol(self):
        self.assertEqual(venues.build("binance_futures").market("PAXG"), "paxgusdt")

    def test_url_is_one_stream(self):
        url = venues.build("binance_futures").url("BTC")
        self.assertTrue(url.endswith("/ws/btcusdt@bookTicker"))


class TestBybit(unittest.TestCase):
    def test_parses_orderbook_one(self):
        v = venues.build("bybit_linear")
        recs = v.parse(FRAMES["bybit_linear"][0], 55, "BTC")
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["b"], 62440.5)
        self.assertEqual(recs[0]["a"], 62440.6)
        self.assertEqual(recs[0]["x"], 1795019269196)

    def test_ignores_other_topics(self):
        v = venues.build("bybit_linear")
        ws = '{"topic":"orderbook.50.ETHUSDT","data":{}}'
        self.assertEqual(v.parse(ws, 1, "BTC"), [])


class TestOkx(unittest.TestCase):
    def test_swap(self):
        v = venues.build("okx_swap")
        recs = v.parse(FRAMES["okx_swap"][0], 10, "BTC")
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["b"], 62445.8)
        self.assertEqual(recs[0]["s"], "BTC")

    def test_spot_symbol(self):
        v = venues.build("okx_spot")
        self.assertEqual(v.market("PAXG"), "PAXG-USDT")
        self.assertEqual(v.market("XAUT-USDT"), "XAUT-USDT")

    def test_spot_frame(self):
        v = venues.build("okx_spot")
        recs = v.parse(FRAMES["okx_spot"][0], 3, "PAXG")
        self.assertEqual(len(recs), 1)
        self.assertAlmostEqual(recs[0]["b"], 3737.9)

    def test_rejects_malformed(self):
        v = venues.build("okx_swap")
        self.assertEqual(v.parse("not json", 1, "BTC"), [])
        self.assertEqual(v.parse('{"arg":{"channel":"bbo-tbt"},"data":[]}', 1, "BTC"), [])


class TestRegistry(unittest.TestCase):
    def test_all_known(self):
        for name in ("hyperliquid", "binance_futures", "bybit_linear", "okx_swap", "okx_spot"):
            self.assertEqual(venues.build(name).name, name)

    def test_unknown(self):
        with self.assertRaises(KeyError):
            venues.build("nasdaq")


if __name__ == "__main__":
    unittest.main()
