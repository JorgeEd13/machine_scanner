"""Tests for the registry runner — isolation, filtering, and a full scan.

These run offline and make no assumptions about the host's hardware (only that
the OS exposes *something*), so they are safe in CI.
"""

import pytest

from machine_scanner.core import registry
from machine_scanner.core.models import Section, Status


def test_available_lists_known_collectors():
    names = registry.available()
    for expected in ("system", "cpu", "memory", "disk", "network", "gpu"):
        assert expected in names


def test_run_all_produces_a_section_per_collector():
    inv = registry.run_all()
    assert len(inv.sections) == len(registry.available())
    assert inv.meta["tool"] == "machine_scanner"


def test_only_filters_collectors():
    inv = registry.run_all(only=["cpu", "memory"])
    names = [s.name for s in inv.sections]
    assert names == ["cpu", "memory"]


def test_unknown_only_name_is_ignored():
    inv = registry.run_all(only=["does-not-exist"])
    assert inv.sections == []


def test_failing_collector_is_isolated(monkeypatch):
    # A collector that raises must become an ERROR section, not crash the scan.
    def boom() -> Section:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(registry, "_REGISTRY", [("explode", boom)])
    inv = registry.run_all()
    assert len(inv.sections) == 1
    sec = inv.sections[0]
    assert sec.status is Status.ERROR
    assert any("kaboom" in n for n in sec.notes)


def test_system_section_always_ok():
    # The stdlib-only collector must succeed everywhere.
    inv = registry.run_all(only=["system"])
    assert inv.section("system").status is Status.OK


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
