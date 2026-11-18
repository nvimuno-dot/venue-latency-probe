"""Command line. Three short measurements and one replay.

    python -m vprobe venue --symbol BTC --seconds 12
    python -m vprobe gold --seconds 8
    python -m vprobe all --save data/mine.json
    python -m vprobe replay data/sample_snapshot.json
"""

from __future__ import annotations

import argparse
import json
import sys

from . import gold, probe, report, venues


def _print_json(obj) -> None:
    json.dump(obj, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true", help="print the analysis as JSON")
    p.add_argument("--save", metavar="PATH", help="write the raw capture to PATH")


def cmd_venue(args) -> int:
    names = [n.strip() for n in args.venues.split(",") if n.strip()] if args.venues \
        else list(probe.DEFAULT_VENUES)
    snapshot = probe.capture(venue_names=names, symbol=args.symbol, seconds=args.seconds)
    if args.save:
        probe.save(snapshot, args.save)
    result = probe.analyse(snapshot)
    if args.json:
        _print_json(result)
    else:
        print(report.render(result))
    if not any(v.get("status") == "ok" for v in result["venues"].values()):
        print("\nno venue answered; check the network path and the symbol", file=sys.stderr)
        return 2
    return 0


def cmd_gold(args) -> int:
    snapshot = gold.capture(seconds=args.seconds)
    if args.save:
        probe.save(snapshot, args.save)
    result = gold.analyse(snapshot)
    if args.json:
        _print_json(result)
    else:
        print(report.render_gold_only(result))
    if not any(v.get("status") == "ok" for v in result["legs"].values()):
        print("\nno gold leg answered; the token markets may be blocked on this path",
              file=sys.stderr)
        return 2
    return 0


def cmd_all(args) -> int:
    names = [n.strip() for n in args.venues.split(",") if n.strip()] if args.venues \
        else list(probe.DEFAULT_VENUES)
    snapshot = probe.capture(venue_names=names, symbol=args.symbol, seconds=args.seconds)
    snapshot["gold"] = gold.capture(seconds=args.gold_seconds)
    if args.save:
        probe.save(snapshot, args.save)
    result = probe.analyse(snapshot)
    if args.json:
        _print_json(result)
    else:
        print(report.render(result))
    return 0


def cmd_replay(args) -> int:
    snapshot = probe.load(args.path)
    result = probe.analyse(snapshot)
    if args.json:
        _print_json(result)
    else:
        print(report.render(result))
    return 0


def cmd_venues(args) -> int:
    for name, cls in sorted(venues.TABLE.items()):
        print(f"{name:<18} {cls.__doc__.strip().splitlines()[0] if cls.__doc__ else ''}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="vprobe",
        description="Snapshot public top-of-book latency, spread and cross-venue "
                    "dispersion, plus the premium on gold tokens and perps.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_venue = sub.add_parser("venue", help="connect, subscribe, and summarise each venue")
    p_venue.add_argument("--symbol", default=probe.DEFAULT_SYMBOL)
    p_venue.add_argument("--seconds", type=float, default=12.0)
    p_venue.add_argument("--venues", help="comma separated; default all four")
    _common(p_venue)

    p_gold = sub.add_parser("gold", help="snapshot gold tokens and perps against spot")
    p_gold.add_argument("--seconds", type=float, default=8.0)
    _common(p_gold)

    p_all = sub.add_parser("all", help="venue snapshot plus gold snapshot")
    p_all.add_argument("--symbol", default=probe.DEFAULT_SYMBOL)
    p_all.add_argument("--seconds", type=float, default=12.0)
    p_all.add_argument("--gold-seconds", type=float, default=8.0)
    p_all.add_argument("--venues", help="comma separated; default all four")
    _common(p_all)

    p_replay = sub.add_parser("replay", help="re-analyse a saved capture, no socket")
    p_replay.add_argument("path")
    p_replay.add_argument("--json", action="store_true")

    sub.add_parser("venues", help="list supported venues")

    args = parser.parse_args(argv)
    table = {"venue": cmd_venue, "gold": cmd_gold, "all": cmd_all,
             "replay": cmd_replay, "venues": cmd_venues}
    return table[args.command](args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
