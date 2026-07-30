"""Platform helpers shared by collectors.

Three things every collector tends to need and that are easy to get wrong:

1. *Which OS am I on* — normalized to "windows" / "linux" / "macos" / "other".
2. *Am I elevated* — some details (BIOS serials, DMI, full disk SMART) need
   admin/root; we report the privilege level so the report can say "run as
   admin for more" instead of silently returning blanks.
3. *Run an OS command safely* — a single guarded `subprocess` wrapper so no
   collector hangs the whole scan or crashes on a missing binary.
"""

from __future__ import annotations

import os
import platform
import subprocess

# Windows PowerShell 5.1 writes stdout in the console **OEM** code page (e.g.
# cp850 on a pt-BR box), not UTF-8. Prefixing a PowerShell command with this
# forces UTF-8 output so `run_command` (which decodes as UTF-8) reads accented
# device names correctly instead of mojibake. A no-BOM UTF8Encoding is used so
# the emitted JSON has no leading BOM to trip `json.loads`.
POWERSHELL_UTF8 = "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false; "


def current_os() -> str:
    """Return a normalized OS name: windows | linux | macos | other."""
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    if system in ("windows", "linux"):
        return system
    return "other"


def is_admin() -> bool:
    """Best-effort check for elevated privileges (admin on Windows, root else).

    Never raises — an unknown answer degrades to ``False`` so callers can treat
    "maybe elevated" the same as "not elevated" (i.e. add the caveat note).
    """
    if current_os() == "windows":
        try:
            import ctypes

            return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
        except Exception:
            return False
    try:
        return os.geteuid() == 0  # type: ignore[attr-defined]
    except AttributeError:
        return False


def run_command(args: list[str], timeout: float = 5.0) -> str | None:
    """Run a command and return stdout, or ``None`` on any failure.

    Guards the three failure modes that would otherwise break a scan: the
    binary is missing (``FileNotFoundError``), it hangs (``timeout``), or it
    exits non-zero.

    Output is decoded as **UTF-8** with ``errors="replace"`` rather than the
    locale default. The locale code page (cp1252 on a pt-BR Windows) silently
    *mis-decodes* the OEM-code-page bytes PowerShell emits — turning ``ç`` into
    ``‡`` and ``ã`` into ``Æ`` — so the corruption lands in the captured data,
    not just the console. Linux/macOS tools already emit UTF-8, and PowerShell
    is forced to UTF-8 via :data:`POWERSHELL_UTF8`, so UTF-8 is correct for
    every source we shell out to.
    """
    try:
        out = subprocess.run(
            args,
            capture_output=True,
            timeout=timeout,
            check=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return out.stdout
    except Exception:
        return None
