# TIERSHEET

Four checks that decide whether a lead-lag or basis number is real. Free, no
email, no signup. If a claim fails one of these, the claim is the problem, not
the market.

---

## Check 1. Can the venue resolve the delay you are measuring?

Two numbers, from the receiving venue:

- updates per second, and the median gap between consecutive quotes
- your measurement window

If your window is shorter than the median gap, you are measuring the venue's
tick granularity, not a delay. A book that prints a new touch every 75 ms cannot
tell you anything about a 10 ms difference, and a window difference computed on
it will show a negative correlation with the next move, because the measure is
mostly its own noise.

Reference, one home connection in Seoul, BTC, six seconds:

| venue | updates/s | median gap |
|---|---|---|
| Hyperliquid | 11.0 | 75 ms |
| Binance USD-M | 376.5 | under 1 ms |
| OKX swap | 62.4 | 11 ms |
| Bybit linear | 47.0 | 10 ms |

## Check 2. Does the gap clear the hurdle before you look at a chart?

Write the round trip down first:

```
hurdle = entry fee + exit fee + slippage + funding (if the position is held)
default: 1.5 bps maker, 4.5 bps taker
maker in, maker out with a taker fallback = 6.0 bps before slippage
```

Then count. Of the anchors whose gap reached 5 bps, how many cleared 7 bps, and
what was the mean forward move on those that did? In the two-minute sample that
shipped with the research kit: 8 of 88 cleared, mean forward move +0.17 bps.

A share above the hurdle is not a strategy. It is the population you are allowed
to look at.

## Check 3. Hit rate and expectancy, always together

Report three numbers, never one:

```
hit rate              share of trades whose sign was right
mean win / mean loss   the two magnitudes
expectancy             hit rate * mean win + (1 - hit rate) * mean loss
```

An 88 percent hit rate with a mean forward move of -0.42 bps is a strategy whose
losses are larger and rarer than its wins. Both numbers come from the same
trades. Quoting only the first is a choice, and it is the wrong one.

## Check 4. A basis is a toll until the cost says otherwise

For any cross-venue premium, in basis points:

```
premium  = (mid leg A - mid leg B) / mid leg B * 10000
cost     = fee A + fee B + conversion or redemption + financing + slippage
```

The premium has to exceed the cost, at the time you can actually trade it, and
on the size you can actually get. Three things invalidate the comparison before
it starts:

- prices read at different timestamps
- a gross spread priced without the conversion cost (refining and freight for
  futures, redemption and issuer fees for tokens)
- a funding interval that changed after your carry model was calibrated

Worked example, six seconds in November 2026: PAXG spot 3,737.75, Binance PAXGUSDT
perp 3,735.00, Hyperliquid PAXG perp 3,735.00. Both perps about 7 bps below spot,
about 0.01 bps apart from each other. Whether that 7 bps is reachable depends on
the funding to hold both legs and the fee to cross each; the number itself is the
easy part.

---

## The one rule that outranks these

Publish the capture with the claim: date, venue set, window, and the file. A
lead-lag claim without a capture is an opinion. `vprobe` writes one with
`--save`.
