"""Small statistics helpers, written out so the probe installs nowhere."""

from __future__ import annotations


def median(values: list[float]) -> float | None:
    """Middle value, averaging the two middles for an even count."""
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def quantile(values: list[float], q: float) -> float | None:
    """Linear-interpolated quantile, q in [0, 1]."""
    if not values:
        return None
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be in [0, 1]")
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    frac = pos - lo
    return s[lo] * (1.0 - frac) + s[hi] * frac


def bps(a: float, b: float) -> float:
    """``a`` relative to ``b`` in basis points."""
    if b == 0:
        raise ZeroDivisionError("reference price is zero")
    return (a - b) / b * 10_000.0


def mid(bid: float, ask: float) -> float:
    return (bid + ask) / 2.0


def spread_bps(bid: float, ask: float) -> float:
    """Quoted spread as a fraction of the mid, in basis points."""
    m = mid(bid, ask)
    if m <= 0:
        raise ValueError("non-positive mid")
    return (ask - bid) / m * 10_000.0


def median_interval_ms(timestamps_ms: list[int]) -> float | None:
    """Median gap between consecutive arrivals, ignoring the first record."""
    if len(timestamps_ms) < 2:
        return None
    diffs = [b - a for a, b in zip(timestamps_ms, timestamps_ms[1:]) if b >= a]
    return median([float(d) for d in diffs])
