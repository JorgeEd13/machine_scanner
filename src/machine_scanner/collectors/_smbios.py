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
from typing import Dict, List, Optional

from ..core.platform import run_command

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


def clean(value: object) -> Optional[str]:
    """Strip a SMBIOS string and reduce vendor placeholders to ``None``."""
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in _PLACEHOLDERS:
        return None
    return text or None


def run_cim(ps_script: str, timeout: float = 20.0) -> Optional[List[Dict]]:
    """Run a PowerShell CIM script that emits JSON; return a list of records.

    Returns ``None`` if the command failed or produced no parseable output, and
    a (possibly empty) ``list[dict]`` otherwise — a single CIM row that
    PowerShell serialized as a bare object is wrapped into a one-element list so
    callers never have to special-case it.
    """
    raw = run_command(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
        timeout=timeout,
    )
    if not raw or not raw.strip():
        return None
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        return None
    if obj is None:
        return None
    if isinstance(obj, dict):
        return [obj]
    if isinstance(obj, list):
        return [row for row in obj if isinstance(row, dict)]
    return None
