"""The tool must stay useful when psutil is absent.

psutil is an optional dependency: collectors that lean on it should degrade to
PARTIAL/UNAVAILABLE with a clear note instead of raising. We simulate "psutil
not installed" by pointing ``_psutil.get`` at ``None`` for the duration of the
test, then assert each collector's documented fallback.
"""

import pytest

from machine_scanner.collectors import _psutil, cpu, disk, memory, network
from machine_scanner.core.models import Status


@pytest.fixture
def no_psutil(monkeypatch):
    monkeypatch.setattr(_psutil, "get", lambda: None)


def test_network_degrades_to_partial(no_psutil):
    sec = network.collect()
    assert sec.status is Status.PARTIAL
    assert any("psutil" in note for note in sec.notes)
    # Still returns the stdlib-derived fields, just not the psutil-only ones.
    assert "hostname" in sec.data
    assert "interfaces" not in sec.data


def test_disk_unavailable(no_psutil):
    sec = disk.collect()
    assert sec.status is Status.UNAVAILABLE
    assert any("psutil" in note for note in sec.notes)


def test_memory_unavailable(no_psutil):
    sec = memory.collect()
    assert sec.status is Status.UNAVAILABLE
    assert any("psutil" in note for note in sec.notes)


def test_cpu_partial_keeps_stdlib_fields(no_psutil):
    sec = cpu.collect()
    assert sec.status is Status.PARTIAL
    assert "cores_logical" in sec.data  # from os.cpu_count(), no psutil needed
    assert any("psutil" in note for note in sec.notes)


def test_no_collector_raises_without_psutil(no_psutil):
    # The guarantee: an absent optional dependency is never an exception.
    for collect in (network.collect, disk.collect, memory.collect, cpu.collect):
        sec = collect()
        assert sec.status is not Status.ERROR
