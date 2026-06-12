"""Command-line interface.

    machine-scanner                 # human-readable report to stdout
    machine-scanner --json          # JSON to stdout
    machine-scanner --html -o report.html
    machine-scanner --only cpu,memory,network
    machine-scanner --list          # list available collectors
    machine-scanner --report        # write + open an HTML report (one-shot)
    machine-scanner --diff old.json new.json        # text diff of two scans
    machine-scanner --diff old.json new.json --html -o diff.html

Double-clicking the packaged binary (no arguments) runs ``--report``: a console
that flashes and closes is useless, so the frozen, no-args case writes an HTML
report next to the binary and opens it in the browser instead.
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path

from . import __version__
from .core.models import Status
from .core.registry import available, run_all
from .report import diff_scans, diff_to_html, diff_to_text, to_html, to_json, to_text
from .report_name import report_filename

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
    parser.add_argument(
        "--report",
        action="store_true",
        help="write an HTML report to a file and open it in the browser "
        "(also the default when the packaged binary is double-clicked)",
    )
    parser.add_argument(
        "--diff",
        nargs=2,
        metavar=("OLD.json", "NEW.json"),
        help="diff two saved JSON scans (text by default; --html / --json change the form)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _emit(rendered: str, out: str | None) -> None:
    """Write a rendered report to a file or stdout (UTF-8 safe on Windows)."""
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(rendered)
        print(f"wrote {out}", file=sys.stderr)
    else:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        print(rendered)


def _is_frozen() -> bool:
    """True when running as a PyInstaller-frozen binary (``sys.frozen``)."""
    return bool(getattr(sys, "frozen", False))


def _run_report(out: str | None) -> int:
    """Scan, write a self-contained HTML report and open it in the browser.

    This is the double-click experience for the packaged binary: a console that
    flashes and closes helps no one, so a no-args frozen run lands here and
    leaves a viewable artifact next to the binary. The filename is localized by
    the OS UI language (filename only — content stays English); ``-o`` overrides
    it. Opening the browser is best-effort and never fails the run.
    """
    inventory = run_all()
    path = Path(out) if out else Path(report_filename())
    path.write_text(to_html(inventory), encoding="utf-8")
    print(f"wrote {path}", file=sys.stderr)
    try:
        webbrowser.open(path.resolve().as_uri())
    except Exception:
        pass  # headless / no browser — the file on disk is the deliverable
    errored = any(s.status is Status.ERROR for s in inventory.sections)
    return EXIT_COLLECTOR_ERROR if errored else EXIT_OK


def _run_diff(paths: list[str], as_html: bool, as_json: bool, out: str | None) -> int:
    """Load two saved JSON scans, diff them, render and emit. No re-scan."""
    old_path, new_path = paths
    try:
        with open(old_path, encoding="utf-8") as fh:
            old = json.load(fh)
        with open(new_path, encoding="utf-8") as fh:
            new = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: could not read scans to diff: {exc}", file=sys.stderr)
        return EXIT_COLLECTOR_ERROR

    diff = diff_scans(old, new)
    if as_json:
        rendered = json.dumps(diff, indent=2, ensure_ascii=False)
    elif as_html:
        rendered = diff_to_html(diff)
    else:
        rendered = diff_to_text(diff)
    _emit(rendered, out)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    raw = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(argv)

    if args.list:
        print("\n".join(available()))
        return EXIT_OK

    # Report mode: explicit --report, or a double-clicked frozen binary (no
    # args). The frozen+no-args gate keeps the normal CLI default (text to
    # stdout) untouched for a terminal run of either the binary or the script.
    if args.report or (_is_frozen() and not raw):
        return _run_report(args.out)

    if args.diff:
        return _run_diff(args.diff, args.html, args.json, args.out)

    only = [s.strip() for s in args.only.split(",")] if args.only else None
    inventory = run_all(only=only)

    if args.json:
        rendered = to_json(inventory)
    elif args.html:
        rendered = to_html(inventory)
    else:
        rendered = to_text(inventory)

    # _emit reconfigures stdout to UTF-8 on Windows so the report never crashes
    # on a non-ASCII device name in a legacy code page.
    _emit(rendered, args.out)

    errored = any(s.status is Status.ERROR for s in inventory.sections)
    return EXIT_COLLECTOR_ERROR if errored else EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
