"""Command-line interface.

    machine-scanner                 # human-readable report to stdout
    machine-scanner --json          # JSON to stdout
    machine-scanner --html -o report.html
    machine-scanner --only cpu,memory,network
    machine-scanner --list          # list available collectors
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .core.models import Status
from .core.registry import available, run_all
from .report import to_html, to_json, to_text

# Exit codes: 0 = clean, 2 = at least one collector hit a genuine bug (ERROR).
# Expected gaps (PARTIAL / UNAVAILABLE / UNSUPPORTED) are not failures.
EXIT_OK = 0
EXIT_COLLECTOR_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="machine-scanner",
        description="Portable, cross-platform machine inventory (hardware / OS / network).",
    )
    fmt = parser.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", help="output JSON")
    fmt.add_argument("--html", action="store_true", help="output a self-contained HTML report")
    parser.add_argument(
        "--only",
        metavar="A,B,C",
        help="comma-separated collectors to run (default: all). See --list.",
    )
    parser.add_argument(
        "-o", "--out", metavar="FILE", help="write to FILE instead of stdout"
    )
    parser.add_argument(
        "--list", action="store_true", help="list available collectors and exit"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list:
        print("\n".join(available()))
        return EXIT_OK

    only = [s.strip() for s in args.only.split(",")] if args.only else None
    inventory = run_all(only=only)

    if args.json:
        rendered = to_json(inventory)
    elif args.html:
        rendered = to_html(inventory)
    else:
        rendered = to_text(inventory)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(rendered)
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        # reconfigure stdout to UTF-8 on Windows so the report never crashes on
        # a non-ASCII device name in a legacy code page.
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        print(rendered)

    errored = any(s.status is Status.ERROR for s in inventory.sections)
    return EXIT_COLLECTOR_ERROR if errored else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
