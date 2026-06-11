"""Tests for the physical memory-modules collector.

Offline and hardware-agnostic: each OS path is driven through a stubbed
``run_command`` / ``_smbios.run_cim``. Covers size/speed/type parsing, the
root-needed degradation on Linux, empty-slot dropping, and never-raises.
"""

import pytest

from machine_scanner.collectors import memory_modules as mm
from machine_scanner.core.models import Status


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("8192 MB", 8.0),
        ("8 GB", 8.0),
        ("16 GB", 16.0),
        ("No Module Installed", None),
        ("Unknown", None),
        ("", None),
    ],
)
def test_size_to_gb(raw, expected):
    assert mm._size_to_gb(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [("3200 MT/s", 3200), ("2667 MHz", 2667), ("Unknown", None), ("", None)],
)
def test_speed_to_mhz(raw, expected):
    assert mm._speed_to_mhz(raw) == expected


@pytest.mark.parametrize(
    "code, expected",
    [(26, "DDR4"), (34, "DDR5"), (24, "DDR3"), (0, None), (2, None), (99, "type 99"), (None, None)],
)
def test_type_label(code, expected):
    assert mm._type_label(code) == expected


# --------------------------------------------------------------------------- #
# Windows / CIM
# --------------------------------------------------------------------------- #

def test_windows_parses_modules(monkeypatch):
    rows = [
        {
            "DeviceLocator": "ChannelA-DIMM0",
            "Capacity": 8589934592,  # 8 GiB
            "ConfiguredClockSpeed": 2400,
            "Speed": 2667,
            "Manufacturer": "Samsung",
            "PartNumber": "M471A1K43CB1-CRC",
            "SMBIOSMemoryType": 26,
        },
        {
            "DeviceLocator": "ChannelB-DIMM0",
            "Capacity": "8589934592",  # string form also accepted
            "ConfiguredClockSpeed": 2400,
            "Manufacturer": "Unknown",  # placeholder -> dropped
            "PartNumber": "M471A1K43CB1-CRC",
            "SMBIOSMemoryType": 26,
        },
    ]
    monkeypatch.setattr(mm._smbios, "run_cim", lambda *a, **k: rows)

    sec = mm._collect_windows()

    assert sec.status is Status.OK
    assert sec.data["count"] == 2
    assert sec.data["total_gb"] == 16.0
    m0 = sec.data["modules"][0]
    assert m0["capacity_gb"] == 8.0
    assert m0["speed_mhz"] == 2400  # ConfiguredClockSpeed preferred over Speed
    assert m0["type"] == "DDR4"
    assert "manufacturer" not in sec.data["modules"][1]  # placeholder scrubbed


def test_windows_command_failure_is_unavailable(monkeypatch):
    monkeypatch.setattr(mm._smbios, "run_cim", lambda *a, **k: None)
    sec = mm._collect_windows()
    assert sec.status is Status.UNAVAILABLE
    assert sec.status is not Status.ERROR


# --------------------------------------------------------------------------- #
# Linux / dmidecode
# --------------------------------------------------------------------------- #

_DMIDECODE = """# dmidecode 3.3
Memory Device
\tArray Handle: 0x0010
\tSize: 8192 MB
\tLocator: DIMM 0
\tType: DDR4
\tSpeed: 2667 MT/s
\tManufacturer: SK Hynix
\tPart Number: HMA81GS6CJR8N-VK
\tConfigured Memory Speed: 2400 MT/s

Memory Device
\tArray Handle: 0x0010
\tSize: No Module Installed
\tLocator: DIMM 1
\tType: Unknown
"""


def test_linux_dmidecode_parse_drops_empty_slot():
    modules = mm._parse_dmidecode(_DMIDECODE)
    assert len(modules) == 1  # the empty DIMM 1 is dropped
    m = modules[0]
    assert m["slot"] == "DIMM 0"
    assert m["capacity_gb"] == 8.0
    assert m["type"] == "DDR4"
    assert m["speed_mhz"] == 2400  # Configured Memory Speed wins


def test_linux_needs_root_when_no_output(monkeypatch):
    monkeypatch.setattr(mm, "current_os", lambda: "linux")
    monkeypatch.setattr(mm, "run_command", lambda *a, **k: None)
    monkeypatch.setattr(mm, "is_admin", lambda: False)

    sec = mm.collect()

    assert sec.status is Status.UNAVAILABLE
    assert sec.status is not Status.ERROR
    assert any("root" in n for n in sec.notes)


# --------------------------------------------------------------------------- #
# macOS
# --------------------------------------------------------------------------- #

_MAC_MEM = """Memory:

      BANK 0/DIMM0:

          Size: 8 GB
          Type: DDR3
          Speed: 1600 MHz
          Manufacturer: 0x802C
          Part Number: 0x12345

      BANK 1/DIMM0:

          Size: 8 GB
          Type: DDR3
          Speed: 1600 MHz
"""


def test_macos_parse(monkeypatch):
    monkeypatch.setattr(mm, "current_os", lambda: "macos")
    monkeypatch.setattr(mm, "run_command", lambda *a, **k: _MAC_MEM)

    sec = mm.collect()

    assert sec.status is Status.OK
    assert sec.data["count"] == 2
    assert sec.data["total_gb"] == 16.0
    assert sec.data["modules"][0]["slot"] == "BANK 0/DIMM0"
    assert sec.data["modules"][0]["type"] == "DDR3"


# --------------------------------------------------------------------------- #
# unsupported + never-raises
# --------------------------------------------------------------------------- #

def test_unsupported_os(monkeypatch):
    monkeypatch.setattr(mm, "current_os", lambda: "other")
    sec = mm.collect()
    assert sec.status is Status.UNSUPPORTED


def test_collect_never_raises_on_real_host():
    sec = mm.collect()
    assert sec.name == "memory_modules"
    assert sec.status is not Status.ERROR


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
