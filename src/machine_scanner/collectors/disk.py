"""Disk collector — mounted partitions and their usage.

Physical drive details (model, serial, SMART health) need OS-specific commands
and often elevation; those are deferred to a later phase. This reports the
logical view (partitions / filesystems / free space), which is the most useful
at-a-glance information and needs no privileges.
"""

from __future__ import annotations

from ..core.models import Section, Status
from ..core.registry import register
from . import _psutil

_GB = 1024 ** 3


def _gb(num_bytes: int) -> float:
    return round(num_bytes / _GB, 2)


@register("disk")
def collect() -> Section:
    ps = _psutil.get()
    if ps is None:
        return Section("disk", "Disk", Status.UNAVAILABLE, {}, [_psutil.MISSING_NOTE])

    partitions = []
    notes = []
    for part in ps.disk_partitions(all=False):
        entry = {
            "device": part.device,
            "mountpoint": part.mountpoint,
            "fstype": part.fstype,
        }
        try:
            usage = ps.disk_usage(part.mountpoint)
            entry["total_gb"] = _gb(usage.total)
            entry["used_gb"] = _gb(usage.used)
            entry["free_gb"] = _gb(usage.free)
            entry["percent_used"] = usage.percent
        except (PermissionError, OSError):
            # e.g. an empty CD drive on Windows — record it, skip the usage.
            notes.append(f"usage unavailable for {part.device}")
        partitions.append(entry)

    return Section("disk", "Disk", Status.OK, {"partitions": partitions}, notes)
