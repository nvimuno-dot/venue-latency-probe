# Two captures, ten minutes apart

The same command, the same machine, the same venue set, twice. This file exists
because the honest answer to "is this representative?" is no, and the two files
say it better than a paragraph.

```
python3 -m vprobe all --symbol BTC --seconds 6  --gold-seconds 6  --save data/sample_snapshot.json
python3 -m vprobe all --symbol BTC --seconds 10 --gold-seconds 10 --save data/capture_20261119_0155.json.gz
```

Both files ship in `data/`. Replay either without a socket:

```
python3 -m vprobe replay data/sample_snapshot.json
python3 -m vprobe replay data/capture_20261119_0155.json.gz
```

## Capture A, 2026-11-18 16:29:50 UTC, 6 s

| venue | connect | first quote | quotes | upd/s | median gap | spread med |
|---|---|---|---|---|---|---|
| hyperliquid | 224 ms | 368 ms | 65 | 11.0 | 75 ms | 0.16 bps |
| binance_futures | 331 ms | 365 ms | 2,247 | 376.5 | under 1 ms | 0.02 bps |
| okx_swap | 510 ms | 890 ms | 352 | 62.4 | 11 ms | 0.02 bps |
| bybit_linear | 520 ms | 661 ms | 276 | 47.0 | 10 ms | 0.02 bps |

Dispersion 1.17 bps. Gold: PAXG spot (OKX) 3,737.75; Binance PAXGUSDT perp
-7.34 bps; Hyperliquid PAXG perp -7.36 bps; XAUT -1.61 bps.

## Capture B, 2026-11-18 16:34:05 UTC, 10 s

| venue | connect | first quote | quotes | upd/s | median gap | spread med |
|---|---|---|---|---|---|---|
| hyperliquid | 247 ms | 432 ms | 121 | 12.5 | 66 ms | 0.16 bps |
| binance_futures | 345 ms | 390 ms | 11,428 | 1,149.0 | under 1 ms | 0.02 bps |
| okx_swap | 411 ms | 592 ms | 737 | 75.1 | 10 ms | 0.02 bps |
| bybit_linear | 514 ms | 654 ms | 597 | 60.5 | 10 ms | 0.02 bps |

Dispersion 1.51 bps. Gold: Binance PAXGUSDT perp -6.71 bps; Hyperliquid PAXG perp
-6.43 bps; XAUT -1.07 bps; HL vs Binance perp +0.28 bps.

## What moved, and why it matters

- **Binance's update rate tripled** between the two windows, 376 to 1,149 quotes
  per second, on the same quiet price. The venue's own print rate is a function
  of how often the touch changes, so any "updates per second" figure has to
  carry its window and its session. That is why the probe prints the count and
  the median gap together instead of a single rate.
- **Hyperliquid's rate barely moved**, 11.0 to 12.5, and its median gap stayed
  between 66 and 75 ms. The receiving venue's resolution is the stable part, and
  it is the part that bounds any lead-lag claim.
- **The gold basis moved by about 0.5 to 0.9 bps** in five minutes: perps stayed
  6 to 7 bps under the token, while XAUT's discount to PAXG halved. A basis is a
  live number, not a constant, which is the whole argument for measuring it
  yourself instead of quoting a screenshot.
- **Connect time rose monotonically with distance to the endpoint** in both
  windows (Hyperliquid fastest, Bybit slowest from this host), which is a
  property of the path, not of the venue's matching engine. The probe never
  reports a one-way delay for exactly this reason.

Neither capture is a study. Six and ten seconds of one instrument on one home
connection say what the code path does and how far apart the books sit right now.
They say nothing about tomorrow, and the README says so.
