"""Tests for the data model — serialization shape and lookup."""

from machine_scanner.core.models import Inventory, Section, Status


def test_status_serializes_to_plain_string():
    # Status inherits str, so it must come out as the bare value in dicts.
    sec = Section("cpu", "CPU", Status.OK, {"cores": 4})
    assert sec.to_dict()["status"] == "ok"


def test_inventory_to_dict_is_nested_and_complete():
    inv = Inventory(meta={"tool": "machine_scanner"})
    inv.sections.append(Section("memory", "Memory", Status.OK, {"total_gb": 8}))
    d = inv.to_dict()
    assert d["meta"]["tool"] == "machine_scanner"
    assert d["sections"][0]["name"] == "memory"
    assert d["sections"][0]["data"]["total_gb"] == 8


def test_section_lookup_by_name():
    inv = Inventory()
    inv.sections.append(Section("disk", "Disk", Status.OK))
    assert inv.section("disk") is not None
    assert inv.section("gpu") is None


def test_section_defaults_are_independent():
    # Mutable defaults must not be shared between instances.
    a = Section("a", "A")
    b = Section("b", "B")
    a.notes.append("only-a")
    assert b.notes == []
