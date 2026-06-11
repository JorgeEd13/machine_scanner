"""Tests for the plain-text renderer, focused on nested-data rendering.

These lock the behaviour that nested lists/dicts (interface addresses, disk
partitions) print as an indented outline rather than a Python ``repr``.
"""

from machine_scanner.core.models import Inventory, Section, Status
from machine_scanner.report.text_report import to_text


def _inventory(section: Section) -> Inventory:
    return Inventory(meta={"version": "0.1.0"}, sections=[section])


def test_list_of_dicts_renders_as_outline_not_repr():
    sec = Section(
        "disk",
        "Disk",
        Status.OK,
        {"partitions": [{"device": "C:", "fstype": "NTFS"}]},
    )
    text = to_text(_inventory(sec))
    assert "device: C:" in text
    assert "fstype: NTFS" in text
    # The give-away of the old behaviour was a bracketed repr in the output.
    assert "[{" not in text
    assert "'device'" not in text


def test_nested_list_inside_dict_recurses():
    # Network interfaces: a list of dicts, each holding a list of address dicts.
    sec = Section(
        "network",
        "Network",
        Status.OK,
        {
            "interfaces": [
                {
                    "name": "eth0",
                    "addresses": [
                        {"family": "AF_INET", "address": "192.168.0.5"},
                        {"family": "AF_INET6", "address": "fe80::1"},
                    ],
                    "is_up": True,
                }
            ]
        },
    )
    text = to_text(_inventory(sec))
    lines = text.splitlines()

    addr_line = next(line for line in lines if line.strip() == "addresses:")
    name_line = next(line for line in lines if line.strip() == "name: eth0")
    family_line = next(line for line in lines if line.strip() == "family: AF_INET")

    # Nested address fields must sit deeper than the key that contains them.
    addr_indent = len(addr_line) - len(addr_line.lstrip())
    family_indent = len(family_line) - len(family_line.lstrip())
    assert family_indent > addr_indent
    assert "192.168.0.5" in text
    assert "fe80::1" in text
    # No repr leakage of the nested list.
    assert "[{" not in text and "'family'" not in text
    assert name_line  # the scalar field still renders


def test_empty_list_renders_none_marker():
    sec = Section("disk", "Disk", Status.OK, {"partitions": []})
    text = to_text(_inventory(sec))
    assert "(none)" in text


def test_scalar_string_is_not_split_into_chars():
    # A str is a Sequence; it must be treated as a scalar, not a list of chars.
    sec = Section("system", "System", Status.OK, {"os": "Windows"})
    text = to_text(_inventory(sec))
    assert "os: Windows" in text
