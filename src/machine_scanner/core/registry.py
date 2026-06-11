"""Collector registry and runner.

Collectors register themselves with ``@register`` at import time; the runner
imports the `collectors` package (which imports every collector module), then
runs the requested set. Each collector runs inside a guard: if it raises, we
capture the traceback into an ``ERROR`` section instead of aborting the scan.
That isolation is the whole point — a flaky GPU probe must never cost you the
CPU and network inventory.
"""

from __future__ import annotations

import datetime as _dt
import getpass
import importlib
import platform as _platform
import socket
import traceback
from typing import Callable, List, Optional

from .. import __version__
from . import platform as plat
from .models import Inventory, Section, Status

# A collector is any zero-arg callable returning a Section.
Collector = Callable[[], Section]

_REGISTRY: "list[tuple[str, Collector]]" = []


def register(name: str) -> Callable[[Collector], Collector]:
    """Decorator: register a collector under a stable machine name."""

    def _wrap(func: Collector) -> Collector:
        _REGISTRY.append((name, func))
        return func

    return _wrap


def available() -> List[str]:
    """Names of all registered collectors, in registration order."""
    _ensure_loaded()
    return [name for name, _ in _REGISTRY]


def _ensure_loaded() -> None:
    """Import the collectors package so every collector self-registers."""
    importlib.import_module("machine_scanner.collectors")


def _build_meta() -> dict:
    return {
        "tool": "machine_scanner",
        "version": __version__,
        "scanned_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "os": plat.current_os(),
        "os_detail": _platform.platform(),
        "hostname": socket.gethostname(),
        "user": _safe_user(),
        "elevated": plat.is_admin(),
    }


def _safe_user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def run_all(only: Optional[List[str]] = None) -> Inventory:
    """Run all collectors (or just the ``only`` subset) into an Inventory.

    ``only`` is a list of collector names; unknown names are ignored. A failing
    collector becomes an ``ERROR`` section with the exception text in notes —
    the scan always completes.
    """
    _ensure_loaded()
    wanted = set(only) if only else None

    inv = Inventory(meta=_build_meta())
    for name, func in _REGISTRY:
        if wanted is not None and name not in wanted:
            continue
        try:
            inv.sections.append(func())
        except Exception as exc:  # isolate one bad collector from the rest
            inv.sections.append(
                Section(
                    name=name,
                    title=name.upper(),
                    status=Status.ERROR,
                    notes=[f"{type(exc).__name__}: {exc}", traceback.format_exc()],
                )
            )
    return inv
