"""Lazy, optional access to psutil.

psutil is the cross-platform backbone (CPU / memory / disk / network in one
library) but we never want its absence to crash the tool — a collector should
degrade to UNAVAILABLE with a clear note instead. Import through ``get()`` and
handle ``None``.
"""

from __future__ import annotations

from typing import Any, Optional

_psutil: Optional[Any] = None
_tried = False


def get() -> Optional[Any]:
    """Return the psutil module, or ``None`` if it isn't installed."""
    global _psutil, _tried
    if not _tried:
        _tried = True
        try:
            import psutil  # type: ignore

            _psutil = psutil
        except Exception:
            _psutil = None
    return _psutil


MISSING_NOTE = "psutil not installed — install it for full detail (pip install psutil)"
