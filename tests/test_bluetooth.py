"""Tests for the bluetooth collector (offline — no real radio touched)."""

import pytest

from machine_scanner.collectors import bluetooth as b
from machine_scanner.core.models import Status

# --------------------------------------------------------------------------- #
# Windows / CIM
# --------------------------------------------------------------------------- #

def test_windows_classifies_adapter_and_devices(monkeypatch):
    rows = [
        {"Name": "Intel(R) Wireless Bluetooth(R)", "Manufacturer": "Intel",
         "PNPDeviceID": r"USB\VID_8087&PID_0026\5&abc"},
        {"Name": "WH-1000XM4", "Manufacturer": "Sony",
         "PNPDeviceID": r"BTHENUM\DEV_AABBCCDDEEFF\7&123&0&AABBCCDDEEFF_C00000000"},
        {"Name": "Headset profile", "Manufacturer": None,
         "PNPDeviceID": r"BTHENUM\{0000110b-0000-1000-8000-00805f9b34fb}_LOCALMFG"},
    ]
    monkeypatch.setattr(b._smbios, "run_cim", lambda *a, **k: rows)
    sec = b._collect_windows()
    assert sec.name == "bluetooth"
    assert sec.status is Status.OK
    assert sec.data["adapter_count"] == 1
    assert sec.data["device_count"] == 1  # the service/profile node is dropped
    assert sec.data["adapters"][0]["name"] == "Intel(R) Wireless Bluetooth(R)"
    dev = sec.data["devices"][0]
    assert dev["name"] == "WH-1000XM4"
    assert dev["address"] == "aa:bb:cc:dd:ee:ff"


def test_windows_empty_is_clean_unavailable(monkeypatch):
    monkeypatch.setattr(b._smbios, "run_cim", lambda *a, **k: [])
    sec = b._collect_windows()
    assert sec.status is Status.UNAVAILABLE
    assert sec.status is not Status.ERROR


def test_windows_query_failure_is_unavailable(monkeypatch):
    monkeypatch.setattr(b._smbios, "run_cim", lambda *a, **k: None)
    sec = b._collect_windows()
    assert sec.status is Status.UNAVAILABLE


# --------------------------------------------------------------------------- #
# Linux / bluetoothctl + sysfs
# --------------------------------------------------------------------------- #

_BTCTL = """Device AA:BB:CC:DD:EE:FF WH-1000XM4
Device 11:22:33:44:55:66 MX Master 3
"""


def test_linux_bluetoothctl_devices(monkeypatch, tmp_path):
    # one adapter in sysfs + bluetoothctl device list
    hci = tmp_path / "hci0"
    hci.mkdir()
    (hci / "address").write_text("00:11:22:33:44:55\n")
    monkeypatch.setattr(b, "run_command", lambda *a, **k: _BTCTL)
    sec = b._collect_linux(str(tmp_path))
    assert sec.status is Status.OK
    assert sec.data["adapter_count"] == 1
    assert sec.data["device_count"] == 2
    assert sec.data["adapters"][0]["name"] == "hci0"
    assert sec.data["adapters"][0]["address"] == "00:11:22:33:44:55"
    assert sec.data["devices"][0]["address"] == "aa:bb:cc:dd:ee:ff"


def test_linux_adapter_only_when_no_bluetoothctl(monkeypatch, tmp_path):
    hci = tmp_path / "hci0"
    hci.mkdir()
    (hci / "address").write_text("00:11:22:33:44:55\n")
    monkeypatch.setattr(b, "run_command", lambda *a, **k: None)
    sec = b._collect_linux(str(tmp_path))
    assert sec.status is Status.OK
    assert sec.data["adapter_count"] == 1
    assert sec.data["device_count"] == 0
    assert any("no paired-device list" in n for n in sec.notes)


def test_linux_no_stack_is_clean_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(b, "run_command", lambda *a, **k: None)
    sec = b._collect_linux(str(tmp_path / "nonexistent"))
    assert sec.status is Status.UNAVAILABLE
    assert sec.status is not Status.ERROR


def test_parse_bluetoothctl():
    devices = b._parse_bluetoothctl(_BTCTL)
    assert [d["name"] for d in devices] == ["WH-1000XM4", "MX Master 3"]


# --------------------------------------------------------------------------- #
# macOS
# --------------------------------------------------------------------------- #

_MAC_BT = """Bluetooth:

      Bluetooth Controller:
          Address: 11:22:33:44:55:66
          Chipset: BCM_4364
      Connected:
          Magic Keyboard:
              Address: AA:BB:CC:00:11:22
          Magic Mouse:
              Address: AA:BB:CC:00:11:33
      Not Connected:
          Old Speaker:
              Address: DD:EE:FF:00:11:22
"""


def test_macos_parse(monkeypatch):
    monkeypatch.setattr(b, "current_os", lambda: "macos")
    monkeypatch.setattr(b, "run_command", lambda *a, **k: _MAC_BT)
    sec = b.collect()
    assert sec.status is Status.OK
    assert sec.data["adapter_count"] == 1
    assert sec.data["adapters"][0]["address"] == "11:22:33:44:55:66"
    names = [d["name"] for d in sec.data["devices"]]
    assert {"Magic Keyboard", "Magic Mouse", "Old Speaker"} <= set(names)


# --------------------------------------------------------------------------- #
# unsupported + never-raises
# --------------------------------------------------------------------------- #

def test_unsupported_os(monkeypatch):
    monkeypatch.setattr(b, "current_os", lambda: "other")
    assert b.collect().status is Status.UNSUPPORTED


def test_collect_never_raises_on_real_host():
    sec = b.collect()
    assert sec.name == "bluetooth"
    assert sec.status is not Status.ERROR


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
