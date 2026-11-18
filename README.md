# venue-latency-probe

Four public order books, one clock, twelve seconds, no account.

`vprobe` connects to the public top-of-book feeds of Hyperliquid, Binance USD-M,
Bybit and OKX at the same moment, subscribes with no key and no permissions,
and prints what each venue actually did on your network path:

- how long the TLS handshake took, and how long until the first quote arrived
- how many updates per second the feed delivered, and the median gap between them
- the quoted spread, median and tightest
- how far apart the four mids sat, in basis points, at the end of the window
- and, from a second snapshot, the premium on gold: PAXG and XAUT as spot tokens,
  PAXG as a USDT perpetual on Binance, PAXG as a perpetual on Hyperliquid

Python 3.10 or newer. No third-party packages. No API key, no wallet, no orders.

```
python3 -m vprobe venue --symbol BTC --seconds 12
python3 -m vprobe gold  --seconds 8
python3 -m vprobe replay data/sample_snapshot.json     # no socket needed
```

A six-second capture of both snapshots ships in `data/sample_snapshot.json`, so
`replay` prints a real result before you open a connection. Everything below is
from that file. `docs/MEASUREMENTS.md` compares it with a second capture taken
five minutes later, and shows which numbers moved and which did not.

---

## 1. What it printed

Capture of 2026-11-18 16:29:50 UTC, six seconds, BTC, from one home connection
in Seoul.

```
venue            status  connect  first quote  quotes  upd/s  median gap  spread med  spread min       bid       ask
---------------  ------  -------  -----------  ------  -----  ----------  ----------  ----------  --------  --------
hyperliquid          ok   224 ms       368 ms      65   11.0       75 ms        0.16        0.16  62,507.0  62,508.0
binance_futures      ok   331 ms       365 ms   2,247  376.5       <1 ms        0.02        0.02  62,506.0  62,506.1
okx_swap             ok   510 ms       890 ms     352   62.4       11 ms        0.02        0.02  62,509.4  62,509.5
bybit_linear         ok   520 ms       661 ms     276   47.0       10 ms        0.02        0.02  62,502.1  62,502.2
```

Read the fourth column against the fifth. Hyperliquid delivered 11 updates per
second on BTC while Binance delivered 376. The target venue's own quote clock is
the floor on any claim that it "lags" someone: if a book only prints a new touch
every 75 ms at the median, a 250 ms window difference is measuring that venue's
tick granularity, not a delay.

The four mids sat 1.17 bps apart at the end of the window. A round trip costs
several times that, which is the whole problem in one line.

## 2. Why an 88 percent hit rate still loses money

Take a window-differenced lead-lag signal that is right about the direction 88
percent of the time. That number is not a paradox and it is not an error. It is a
statement about the shape of the losses.

On a two-minute BTC and SOL capture across the same four venues, at a 1000 ms
window and a 500 ms horizon, the sign of the gap agreed with the next move 88
percent of the time and the mean forward move was **-0.42 bps**. The winners were
small and frequent, the losers were large and rare, and the average is what pays
the fees.

The screen that follows is arithmetic, not opinion: 1.5 bps maker plus 4.5 bps
taker, a maker entry with a maker exit and a taker fallback, is 6.0 bps before
slippage. Of 88 anchors whose gap reached 5 bps, 8 cleared 7 bps, and the mean
forward move on those was +0.17 bps.

Two things in that paragraph are worth stealing for your own work:

- A hit rate without the conditional mean will flatter a strategy that loses.
  Both numbers come from the same trades; quoting one is a choice.
- The gap has to be measured in returns, not prices. With a constant lag on a
  smooth trend, a window difference is zero, because both returns cover the same
  shape. The gap appears around jumps and reversals, which is exactly where the
  fills are worst.

The probe gives you the two inputs to that test on your own path: the update rate
of the receiving venue, and the quoted spread you have to cross. The rest is in
the kit linked at the bottom.

## 3. Gold has three prices, and a perp that quotes below spot

Same six seconds, gold:

```
leg               rail                status       bid       ask  spread  premium     age
----------------  ------------------  ------  --------  --------  ------  -------  ------
Hyperliquid PAXG  perp, venue oracle  ok      3,734.60  3,735.40    2.14    -7.36  496 ms
Binance PAXGUSDT  USDT perpetual      ok      3,735.00  3,735.01    0.03    -7.34    8 ms
OKX XAUT-USDT     spot token (XAUT)   ok      3,737.10  3,737.20    0.27    -1.61   <1 ms
OKX PAXG-USDT     spot token (PAXG)   ok      3,737.60  3,737.90    0.80     0.00  359 ms
```

Premium is the leg's mid against the spot PAXG mid, in basis points. Both gold
perpetuals quoted about 7 bps below the token that is redeemable for allocated
London bars, for the entire window, on both venues, within 0.01 bps of each
other. XAUT, a different issuer holding the same metal, sat 1.61 bps below PAXG.

That 7 bps is a basis, and a basis is not free money. It is what the funding rate
exists to charge for, and whether it is reachable depends on the cost of holding
both legs and the fee to cross each one. But it is a real, timestamped number
that you can reproduce in eight seconds, and almost nobody publishing gold
"arbitrage" content shows it next to the cost of the trade.

Three rails, three prices, one metal. The London-New York leg is not in this
table because the COMEX contract and the LBMA lease rate are not on a free
public socket, and a delayed print would poison a live cross-venue number. That
bridge needs its own arithmetic.

## 4. The 73 hours

COMEX closes on Friday afternoon and reopens on Sunday evening. That is about 73
hours in which the most liquid gold price in the world does not exist, while the
tokens keep trading and the perpetuals keep marking.

Three venues answer that silence three different ways:

1. A frozen index. The mark stops moving and the perp trades against a number
   that cannot react, so the funding rate becomes the only thing pricing the gap.
2. A bounded average of the venue's own order book, inside a fence. The price can
   move, but only as far as the book and the fence allow, so the fence is the
   real instrument.
3. A continuously traded token, which never closes and therefore never stops
   being wrong in a fast market.

Each design fails differently on a Sunday gap, and the failure is measurable if
you know which mark you are looking at. `vprobe gold` shows you which one your
perp is using, by putting it next to the token that does not close.

## 5. What this does not do

- It does not place orders, hold keys, or sign anything. There is no order
  router and no private endpoint in this repository.
- It does not compute an edge. It prints the inputs: update resolution, spread,
  dispersion, basis. What you do with them is your problem and your risk.
- It does not measure absolute one-way latency. Every timestamp is this
  machine's clock. The venue's own timestamp is kept beside it but never
  subtracted, because the difference contains the clock offset between two
  machines that were never synchronised, and that offset is usually larger than
  the delay you are looking for.
- It does not claim a six-second window is a study. It is a smoke test and a
  sample. Numbers move with the session, the region and the network path.
- Binance spot is geo-blocked on some paths (HTTP 451) and its REST host refuses
  requests from several countries, so every Binance leg here is a USD-M
  perpetual, including the gold one. Bybit's REST endpoints are blocked from
  Korea; its WebSocket is not. The probe reports what answered and names what
  did not.

## 6. Run it, test it

```
python3 --version                      # 3.10 or newer
python3 -m vprobe venues               # what can be connected to
python3 -m vprobe venue --symbol BTC --seconds 12 --save data/mine.json
python3 -m vprobe gold --seconds 8
python3 -m vprobe replay data/mine.json
python3 -m unittest discover -s tests -t .     # 54 tests, no network needed
```

`--json` on any command prints the same analysis as a machine-readable object.
`--venues hyperliquid,okx_swap` narrows the set. Tests use recorded frames from
all five adapters, so the parsers are checked against the venues' real output
rather than against the parser's own assumptions.

## 7. The paid part, labelled plainly

The two write-ups this probe is a doorway to were written by me, and this
repository is the free end of them. If the numbers above are enough, take them
and go; nothing here expires.

- **The Three Bridges of Gold** (30-page PDF, 49 USD): the London vault, the New
  York futures contract and the on-chain oracle, with the EFP cost stack, lease
  rates, the 73-hour weekend gap, six structures priced after costs, and ten
  failure modes. https://baobab-field-press.shopfa.st/products/three-bridges-of-gold
- **Hyperliquid Multi-Venue Market Data and Lead-Lag Research Kit** (100 USD):
  the measurement code this probe is cut from, 40 tests, a two-minute sample
  capture, and a 20-page guide to the definitions and their failure modes.
  https://baobab-field-press.shopfa.st/products/hyperliquid-leadlag-research-kit
- Free, no email: `docs/TIERSHEET.md`, the four checks that decide whether a
  lead-lag or basis claim survives contact with its own fees.

If a number in this README looks wrong, open an issue with your capture file and
the date. A lead-lag claim without a capture is an opinion; that applies to this
one too.

## License

MIT. See `LICENSE`.
