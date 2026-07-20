"""The requirements check as its own program.

`cli.py` inventories a machine. This asks one question — *can it run a local AI
model?* — and it is a separate entry point rather than a flag because of who
runs it: someone who was sent a binary by a stranger and has no reason to trust
it yet.

That shapes two decisions:

**It collects four things.** CPU, memory, GPU, free disk, plus whether Ollama
and Docker are already installed. Not the network interfaces, not the disk
serials, not the USB devices, not the hostname or username. A full inventory
would answer the same question and would also hand over a machine fingerprint
nobody asked for — and the people most likely to run this are the people most
likely to mind. Collecting less is the point, not a limitation.

**It says so in the report.** The scope is printed, so the claim is checkable
against the output rather than taken on faith.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from . import __version__
from .advisor import append_to as append_fit

# Imported one by one, never via the manifest: this is what keeps the collectors
# outside SCOPE out of the frozen binary entirely (ADR-021), so the privacy claim
# describes the artifact and not just its default behaviour.
from .collectors import cpu, disk, gpu, llm_runtime, memory  # noqa: F401
from .core.registry import run_all
from .report.requirements_report import to_requirements_html, to_requirements_text

# The only collectors this runs. Every omission is deliberate; see the module
# docstring before adding one.
SCOPE = ["cpu", "memory", "gpu", "disk", "llm_runtime"]

# Fields dropped from the scan metadata before anything is rendered. The scan
# knows them; the report must not carry them off the machine.
IDENTIFYING_META = ("hostname", "user")

DEFAULT_REPORT = "ai_model_requirements.html"

EXIT_OK = 0


def _scan():
    """Run the scoped collectors and strip identifying metadata."""
    inventory = append_fit(run_all(only=SCOPE, autoload=False))
    for field in IDENTIFYING_META:
        inventory.meta.pop(field, None)
    inventory.meta["scope"] = SCOPE
    return inventory


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-model-requirements",
        description="Check whether this machine can run a local AI model. "
        "Read-only: it installs nothing, changes nothing, and sends nothing.",
    )
    parser.add_argument("--text", action="store_true", help="print the result instead of writing a page")
    parser.add_argument("-o", "--out", metavar="FILE", help="write the page to FILE")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: "list[str] | None" = None) -> int:
    args = build_parser().parse_args(argv)
    inventory = _scan()

    if args.text:
        text = to_requirements_text(inventory)
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        print(text)
        return EXIT_OK

    path = Path(args.out) if args.out else Path(DEFAULT_REPORT)
    path.write_text(to_requirements_html(inventory), encoding="utf-8")
    print(f"wrote {path}", file=sys.stderr)

    # A double-clicked binary whose console flashes and closes has told the user
    # nothing. Opening the page is the whole delivery.
    try:
        webbrowser.open(path.resolve().as_uri())
    except Exception:
        pass

    # Always 0: "your machine cannot run this" is an answer, not a failure, and a
    # non-zero exit would make a launcher or an antivirus sandbox report a crash.
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
