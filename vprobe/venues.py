"""Venue adapters for the public top-of-book feeds.

Each adapter answers three questions and nothing else:

  * what URL do I connect to, and what do I send after connecting
  * how does this venue spell a symbol
  * how do I turn one raw frame into zero or more quote records

A quote record is a plain dict:

  {"v": venue, "s": symbol, "t": local arrival ms, "b": bid, "a": ask,
   "bs": bid size, "as": ask size, "x": the venue's own timestamp, if any}

``t`` is taken as soon as the frame is out of the TLS buffer and before the
JSON is parsed. ``x`` is the venue's clock. The difference between them is not
latency: it also contains the offset between the two machines' clocks. That is
why the probe reports connection and first-quote times measured on one local
clock, and never claims an absolute one-way delay.
"""

from __future__ import annotations

import json
from typing import Any


def _f(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _i(x) -> int | None:
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


class Venue:
    name = "venue"

    def url(self, symbol: str) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def subscribe(self, symbol: str) -> list[str]:
        return []

    def heartbeat(self) -> str | None:
        return None

    def parse(self, raw: str, recv_ms: int, symbol: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def market(self, symbol: str) -> str:
        return symbol.upper()


class Hyperliquid(Venue):
    """Target venue. The ``bbo`` channel: both sides of the touch, whenever
    the touch changes. Symbol is the coin name as Hyperliquid spells it."""

    name = "hyperliquid"

    def url(self, symbol: str) -> str:
        return "wss://api.hyperliquid.xyz/ws"

    def subscribe(self, symbol: str) -> list[str]:
        return [json.dumps({"method": "subscribe",
                            "subscription": {"type": "bbo", "coin": symbol}})]

    def heartbeat(self) -> str | None:
        return json.dumps({"method": "ping"})

    def parse(self, raw: str, recv_ms: int, symbol: str) -> list[dict[str, Any]]:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(msg, dict):
            return []
        channel = msg.get("channel")
        data = msg.get("data")
        if channel == "error":
            raise RuntimeError(f"hyperliquid error frame: {data}")
        if channel != "bbo" or not isinstance(data, dict):
            return []
        if data.get("coin") != symbol:
            return []
        sides = data.get("bbo") or []
        if len(sides) < 2:
            return []
        bid, ask = _f(sides[0].get("px")), _f(sides[1].get("px"))
        if bid <= 0 or ask <= 0 or bid >= ask:
            return []
        return [{"v": self.name, "s": symbol, "t": recv_ms,
                 "b": bid, "a": ask,
                 "bs": round(_f(sides[0].get("sz")), 8),
                 "as": round(_f(sides[1].get("sz")), 8),
                 "x": _i(data.get("time"))}]


class BinanceFutures(Venue):
    """USD-M perpetual best bid/offer: <symbol>@bookTicker, one stream per URL.

    This is the only Binance feed that answered from the network the probe was
    built on. Binance spot is geo-blocked on some paths (HTTP 451) and its REST
    host refuses requests from several countries, so every Binance leg here is
    a USD-M perpetual, including the gold one.
    """

    name = "binance_futures"

    def __init__(self, host: str = "wss://fstream.binance.com") -> None:
        self.host = host.rstrip("/")

    def market(self, symbol: str) -> str:
        return f"{symbol.lower()}usdt"

    def url(self, symbol: str) -> str:
        return f"{self.host}/ws/{self.market(symbol)}@bookTicker"

    def parse(self, raw: str, recv_ms: int, symbol: str) -> list[dict[str, Any]]:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(msg, dict):
            return []
        if "result" in msg and "id" in msg:
            return []
        bid, ask = _f(msg.get("b")), _f(msg.get("a"))
        if bid <= 0 or ask <= 0 or ask < bid:
            return []
        return [{"v": self.name, "s": symbol, "t": recv_ms,
                 "b": bid, "a": ask,
                 "bs": round(_f(msg.get("B")), 8),
                 "as": round(_f(msg.get("A")), 8),
                 "x": _i(msg.get("E") or msg.get("T"))}]


class BybitLinear(Venue):
    """USDT perpetual top of book: orderbook.1.<SYMBOL>."""

    name = "bybit_linear"

    def market(self, symbol: str) -> str:
        return f"{symbol.upper()}USDT"

    def url(self, symbol: str) -> str:
        return "wss://stream.bybit.com/v5/public/linear"

    def subscribe(self, symbol: str) -> list[str]:
        return [json.dumps({"op": "subscribe",
                            "args": [f"orderbook.1.{self.market(symbol)}"]})]

    def heartbeat(self) -> str | None:
        return json.dumps({"op": "ping"})

    def parse(self, raw: str, recv_ms: int, symbol: str) -> list[dict[str, Any]]:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(msg, dict):
            return []
        topic = msg.get("topic", "")
        if not isinstance(topic, str) or not topic.startswith("orderbook.1."):
            return []
        data = msg.get("data") or {}
        bids, asks = data.get("b") or [], data.get("a") or []
        if not bids or not asks:
            return []
        try:
            bid, bid_sz = _f(bids[0][0]), _f(bids[0][1])
            ask, ask_sz = _f(asks[0][0]), _f(asks[0][1])
        except (IndexError, TypeError):
            return []
        if bid <= 0 or ask <= 0 or ask < bid:
            return []
        return [{"v": self.name, "s": symbol, "t": recv_ms,
                 "b": bid, "a": ask,
                 "bs": round(bid_sz, 8), "as": round(ask_sz, 8),
                 "x": _i(msg.get("ts"))}]


class OkxBase(Venue):
    """OKX best bid/offer on the 443 endpoint. ``bbo-tbt`` carries a touch on
    every book change, spot or swap, depending on the instId."""

    name = "okx"
    channel = "bbo-tbt"

    def market(self, symbol: str) -> str:
        raise NotImplementedError

    def url(self, symbol: str) -> str:
        return "wss://ws.okx.com:443/ws/v5/public"

    def subscribe(self, symbol: str) -> list[str]:
        return [json.dumps({"op": "subscribe",
                            "args": [{"channel": self.channel,
                                      "instId": self.market(symbol)}]})]

    def heartbeat(self) -> str | None:
        return "ping"

    def parse(self, raw: str, recv_ms: int, symbol: str) -> list[dict[str, Any]]:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(msg, dict):
            return []
        if msg.get("arg", {}).get("channel") != self.channel:
            return []
        for item in msg.get("data") or []:
            bids, asks = item.get("bids") or [], item.get("asks") or []
            if not bids or not asks:
                continue
            bid, bid_sz = _f(bids[0][0]), _f(bids[0][1])
            ask, ask_sz = _f(asks[0][0]), _f(asks[0][1])
            if bid <= 0 or ask <= 0 or ask < bid:
                continue
            return [{"v": self.name, "s": symbol, "t": recv_ms,
                     "b": bid, "a": ask,
                     "bs": round(bid_sz, 8), "as": round(ask_sz, 8),
                     "x": _i(item.get("ts"))}]
        return []


class OkxSwap(OkxBase):
    """USDT perpetual top of book: BTC-USDT-SWAP."""

    name = "okx_swap"

    def market(self, symbol: str) -> str:
        return f"{symbol.upper()}-USDT-SWAP"


class OkxSpot(OkxBase):
    """Spot top of book, used for the tokenised gold legs: PAXG-USDT, XAUT-USDT."""

    name = "okx_spot"

    def market(self, symbol: str) -> str:
        symbol = symbol.upper()
        return symbol if "-" in symbol else f"{symbol}-USDT"


TABLE = {
    "hyperliquid": Hyperliquid,
    "binance_futures": BinanceFutures,
    "bybit_linear": BybitLinear,
    "okx_swap": OkxSwap,
    "okx_spot": OkxSpot,
}


def build(name: str) -> Venue:
    if name not in TABLE:
        raise KeyError(f"unknown venue {name!r}; known: {', '.join(sorted(TABLE))}")
    return TABLE[name]()
