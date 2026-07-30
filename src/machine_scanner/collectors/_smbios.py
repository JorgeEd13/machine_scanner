"""Shared helpers for the firmware-level collectors (Windows CIM + SMBIOS).

Two small things `baseboard`-style collectors keep needing and that are easy to
get subtly wrong:

1. *Run a CIM query and get records back* — `Get-CimInstance … | ConvertTo-Json`
   through the guarded `run_command`, parsed and **always normalized to a list**
   (PowerShell emits a bare object for a single row and an array for many; that
   asymmetry is a classic parsing bug).
2. *Scrub SMBIOS placeholder junk* — firmware tables are full of "To Be Filled
   By O.E.M.", "Default string", all-`F` UUIDs, etc.; `clean` reduces those to
   ``None`` so a blank field reads as genuinely unknown, not as boilerplate.

This is an underscore-prefixed collector helper (same role as ``_psutil.py``),
not a public collector — it self-registers nothing.
"""

from __future__ import annotations

import json

from ..core.platform import POWERSHELL_UTF8, run_command

# Common SMBIOS placeholder strings (lower-cased) that mean "not really set".
_PLACEHOLDERS = {
    "",
    "to be filled by o.e.m.",
    "to be filled by o.e.m",
    "default string",
    "none",
    "not specified",
    "not available",
    "not applicable",
    "no enclosure",
    "no module installed",
    "unknown",
    "n/a",
    "0",
    "00000000",
    "system serial number",
    "system manufacturer",
    "system product name",
    "system version",
    "base board version",
    "base board serial number",
    "base board asset tag",
    "chassis serial number",
    "fffffffffffffffffffffff",
    "ffffffff-ffff-ffff-ffff-ffffffffffff",
}


def clean(value: object) -> str | None:
    """Strip a SMBIOS string and reduce vendor placeholders to ``None``."""
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in _PLACEHOLDERS:
        return None
    return text or None


def _strip_bom(text: str) -> str:
    """Drop a leading UTF-8 BOM if present (json.loads rejects one).

    Done via a utf-8-sig round-trip so the source stays ASCII (no invisible
    BOM character embedded here). A no-BOM encoding is already forced on the
    PowerShell side, so this is belt-and-suspenders.
    """
    return text.encode("utf-8").decode("utf-8-sig")


def run_cim(ps_script: str, timeout: float = 20.0) -> list[dict] | None:
    """Run a PowerShell CIM script that emits JSON; return a list of records.

    Returns ``None`` if the command failed or produced no parseable output, and
    a (possibly empty) ``list[dict]`` otherwise — a single CIM row that
    PowerShell serialized as a bare object is wrapped into a one-element list so
    callers never have to special-case it.

    The script is prefixed with :data:`POWERSHELL_UTF8` so accented values
    (e.g. a pt-BR device name like ``Aperfeiçoado``) come back intact rather
    than mojibake from the console OEM code page.
    """
    raw = run_command(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            POWERSHELL_UTF8 + ps_script,
        ],
        timeout=timeout,
    )
    if not raw or not raw.strip():
        return None
    try:
        obj = json.loads(_strip_bom(raw))
    except (ValueError, TypeError):
        return None
    if obj is None:
        return None
    if isinstance(obj, dict):
        return [obj]
    if isinstance(obj, list):
        return [row for row in obj if isinstance(row, dict)]
    return None
