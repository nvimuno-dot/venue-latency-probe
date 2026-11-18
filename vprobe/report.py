"""Text rendering. Plain ASCII, fixed columns, no decoration."""

from __future__ import annotations

from . import stats


def _fmt_num(x, digits: int = 0) -> str:
    if x is None:
        return "-"
    if digits == 0:
        return f"{x:,.0f}"
    return f"{x:,.{digits}f}"


def _fmt_ms(x) -> str:
    if x is None:
        return "-"
    if x >= 1000:
        return f"{x/1000:.2f} s"
    if x < 1:
        return "<1 ms"
    if x < 10:
        return f"{x:.1f} ms"
    return f"{x:,.0f} ms"


def _fmt_bps(x, digits: int = 2, signed: bool = False) -> str:
    if x is None:
        return "-"
    sign = "+" if (signed and x > 0) else ""
    return f"{sign}{x:.{digits}f}"


def _table(headers: list[str], rows: list[list[str]], align: str | None = None) -> list[str]:
    """Left-align text columns, right-align numeric ones."""
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    align = align or ("l" + "r" * (len(headers) - 1))
    out = []
    for row_i, row in enumerate([headers] + rows):
        cells = []
        for i, cell in enumerate(row):
            cells.append(cell.ljust(widths[i]) if align[i] == "l" else cell.rjust(widths[i]))
        line = "  ".join(cells).rstrip()
        out.append(line)
        if row_i == 0:
            out.append("  ".join("-" * w for w in widths).rstrip())
    return out


def venue_table(result: dict) -> list[str]:
    rows = []
    order = sorted(result["venues"].keys(),
                   key=lambda n: (result["venues"][n].get("connect_ms") is None,
                                  result["venues"][n].get("connect_ms") or 0))
    for name in order:
        v = result["venues"][name]
        last = v.get("last") or {}
        rows.append([
            name,
            v.get("status") or "-",
            _fmt_ms(v.get("connect_ms")),
            _fmt_ms(v.get("first_quote_ms")),
            _fmt_num(v.get("quotes")),
            _fmt_num(v.get("updates_per_s"), 1),
            _fmt_ms(v.get("median_gap_ms")),
            _fmt_bps(v.get("spread_median_bps")),
            _fmt_bps(v.get("spread_min_bps")),
            _fmt_num(last.get("bid"), 2 if (last.get("bid") or 0) < 1000 else 1),
            _fmt_num(last.get("ask"), 2 if (last.get("ask") or 0) < 1000 else 1),
        ])
    return _table(
        ["venue", "status", "connect", "first quote", "quotes", "upd/s",
         "median gap", "spread med", "spread min", "bid", "ask"],
        rows)


def dispersion_block(result: dict) -> list[str]:
    d = result.get("dispersion") or {}
    lines = []
    if d.get("range_bps") is None:
        lines.append("book dispersion: no two venues answered inside the window")
        return lines
    lines.append(f"book dispersion: {d['range_bps']:.2f} bps between the outer mids "
                 f"across {d['n']} books")
    ref = d.get("ref_mid")
    if ref:
        lines.append(f"  reference mid (median of books): {_fmt_num(ref, 2)}")
    for name, delta in sorted(d["legs"].items(), key=lambda kv: kv[1]):
        lines.append(f"  {name:<18} {_fmt_bps(delta, signed=True)} bps")
    return lines


def gold_block(gold_result: dict) -> list[str]:
    legs = gold_result.get("legs") or {}
    if not legs:
        return ["gold snapshot: no legs captured"]
    rows = []
    order = sorted(legs.keys(), key=lambda k: (legs[k].get("premium_bps") is None,
                                               legs[k].get("premium_bps") or 0))
    for key in order:
        v = legs[key]
        rows.append([
            v.get("label", key),
            v.get("rail", ""),
            v.get("status") or "-",
            _fmt_num((v.get("last") or {}).get("bid"), 2),
            _fmt_num((v.get("last") or {}).get("ask"), 2),
            _fmt_bps(v.get("spread_bps")),
            _fmt_bps(v.get("premium_bps"), signed=True),
            _fmt_ms(v.get("age_ms")) if v.get("age_ms") is not None else "-",
        ])
    lines = ["gold snapshot (premium in bps against the spot anchor)"]
    lines += ["  " + line for line in _table(
        ["leg", "rail", "status", "bid", "ask", "spread", "premium", "age"], rows,
        align="lllrrrrr")]
    anchor = gold_result.get("anchor")
    if anchor:
        lines.append(f"  anchor: {anchor}")
    pairs = gold_result.get("pairs_bps") or {}
    if pairs:
        lines.append("  pair differences (bps):")
        for label, value in pairs.items():
            lines.append(f"    {label:<40} {_fmt_bps(value, signed=True)}")
    return lines


def render(result: dict) -> str:
    lines = []
    lines.append(f"{result.get('tool', 'venue-latency-probe')} {result.get('version', '')}".rstrip())
    lines.append(f"captured {result.get('captured_at') or '-'}   "
                 f"window {result.get('window_s')} s   symbol {result.get('symbol') or '-'}")
    lines.append("timestamps are local arrival times on one clock; venue clocks are not subtracted")
    lines.append("")
    if result.get("venues"):
        lines += venue_table(result)
        notes = [(name, v["error"]) for name, v in result["venues"].items() if v.get("error")]
        if notes:
            lines.append("")
            for name, err in notes:
                lines.append(f"  {name}: {err}")
        lines.append("")
        lines += dispersion_block(result)
    if result.get("gold"):
        lines.append("")
        lines += gold_block(result["gold"])
    lines.append("")
    lines.append("this measures the path and the book: no orders, no keys, no edge calculation")
    return "\n".join(lines)


def render_gold_only(gold_result: dict, captured_at: str | None = None) -> str:
    lines = ["venue-latency-probe gold snapshot"]
    if captured_at:
        lines.append(f"captured {captured_at}   window {gold_result.get('window_s')} s")
    lines.append("")
    lines += gold_block(gold_result)
    lines.append("")
    lines.append("a perp's premium to spot is the basis the funding rate exists to charge for")
    return "\n".join(lines)
