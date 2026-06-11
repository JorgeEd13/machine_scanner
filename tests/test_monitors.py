"""Tests for the monitors collector.

Offline: the Linux path is driven by a hand-built EDID blob in a temp
``/sys/class/drm`` tree; Windows/macOS via stubbed CIM / ``run_command``.
"""

import pytest

from machine_scanner.collectors import monitors as m
from machine_scanner.core.models import Status


def _make_edid(manufacturer="DEL", product=0xA0C1, serial_num=0x12345678, name="DELL U2412M"):
    """Build a minimal valid 128-byte EDID 1.x block."""
    edid = bytearray(128)
    edid[0:8] = m._EDID_HEADER
    packed = ((ord(manufacturer[0]) - 64) << 10) | ((ord(manufacturer[1]) - 64) << 5) | (ord(manufacturer[2]) - 64)
    edid[8] = (packed >> 8) & 0xFF
    edid[9] = packed & 0xFF
    edid[10] = product & 0xFF
    edid[11] = (product >> 8) & 0xFF
    edid[12:16] = serial_num.to_bytes(4, "little")
    # Monitor-name descriptor at offset 54: 00 00 00 FC 00 <text \n padded>
    desc = bytearray(18)
    desc[3] = 0xFC
    text = (name + "\n").encode("latin-1")
    desc[5:5 + len(text)] = text
    for i in range(5 + len(text), 18):
        desc[i] = 0x20
    edid[54:72] = desc
    return bytes(edid)


def test_decode_manufacturer():
    assert m._decode_manufacturer(0x10, 0xAC) == "DEL"  # Dell's PnP ID


def test_parse_edid_full():
    parsed = m._parse_edid(_make_edid())
    assert parsed["manufacturer"] == "DEL"
    assert parsed["product_code"] == "A0C1"
    assert parsed["name"] == "DELL U2412M"


def test_parse_edid_rejects_bad_header():
    assert m._parse_edid(b"\x00" * 128) is None
    assert m._parse_edid(b"\x00\xff\xff") is None  # too short


# --------------------------------------------------------------------------- #
# Linux / sysfs EDID
# --------------------------------------------------------------------------- #

def test_linux_reads_edid(tmp_path):
    connected = tmp_path / "card0-DP-1"
    connected.mkdir()
    (connected / "edid").write_bytes(_make_edid(name="My Display"))
    disconnected = tmp_path / "card0-HDMI-A-1"  # present but nothing plugged in
    disconnected.mkdir()
    (disconnected / "edid").write_bytes(b"")

    sec = m._collect_linux(str(tmp_path))

    assert sec.status is Status.OK
    assert sec.data["count"] == 1
    mon = sec.data["monitors"][0]
    assert mon["name"] == "My Display"
    assert mon["connector"] == "DP-1"


def test_linux_no_drm_dir_is_unavailable():
    sec = m._collect_linux("/nonexistent/drm")
    assert sec.status is Status.UNAVAILABLE
    assert sec.status is not Status.ERROR


# --------------------------------------------------------------------------- #
# Windows / WmiMonitorID (char-code arrays)
# --------------------------------------------------------------------------- #

def test_windows_decode_charcodes(monkeypatch):
    rows = [{
        "ManufacturerName": [68, 69, 76, 0],         # "DEL"
        "UserFriendlyName": [85, 50, 52, 49, 50, 0],  # "U2412"
        "ProductCodeID": [65, 48, 67, 49, 0],         # "A0C1"
        "SerialNumberID": [55, 56, 57, 0],            # "789"
    }]
    monkeypatch.setattr(m._smbios, "run_cim", lambda *a, **k: rows)

    sec = m._collect_windows()

    assert sec.status is Status.OK
    mon = sec.data["monitors"][0]
    assert mon["manufacturer"] == "DEL"
    assert mon["name"] == "U2412"
    assert mon["serial"] == "789"


def test_windows_no_rows_is_unavailable(monkeypatch):
    monkeypatch.setattr(m._smbios, "run_cim", lambda *a, **k: None)
    sec = m._collect_windows()
    assert sec.status is Status.UNAVAILABLE


# --------------------------------------------------------------------------- #
# macOS
# --------------------------------------------------------------------------- #

_MAC_DISPLAYS = """Graphics/Displays:

    Intel Iris:

      Displays:
        Color LCD:
          Resolution: 2560 x 1600 Retina
        DELL U2412M:
          Resolution: 1920 x 1200
"""


def test_macos_parse(monkeypatch):
    monkeypatch.setattr(m, "current_os", lambda: "macos")
    monkeypatch.setattr(m, "run_command", lambda *a, **k: _MAC_DISPLAYS)
    sec = m.collect()
    assert sec.status is Status.OK
    names = [d["name"] for d in sec.data["monitors"]]
    assert "Color LCD" in names and "DELL U2412M" in names


# --------------------------------------------------------------------------- #
# unsupported + never-raises
# --------------------------------------------------------------------------- #

def test_unsupported_os(monkeypatch):
    monkeypatch.setattr(m, "current_os", lambda: "other")
    assert m.collect().status is Status.UNSUPPORTED


def test_collect_never_raises_on_real_host():
    sec = m.collect()
    assert sec.name == "monitors"
    assert sec.status is not Status.ERROR


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
