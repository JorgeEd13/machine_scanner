"""Tests for the USB devices collector (ROADMAP F3).

Offline and hardware-agnostic: each OS path is driven through a stubbed
``run_command`` / ``_smbios.run_cim`` or a temp ``/sys/bus/usb`` directory.
Covers VID/PID extraction, the Linux lsusb→sysfs fallback, macOS tree parsing,
and never-raises.
"""

import pytest

from machine_scanner.collectors import usb
from machine_scanner.core.models import Status


@pytest.mark.parametrize(
    "device_id, expected",
    [
        ("USB\\VID_8087&PID_0024\\5&abc", ("8087", "0024")),
        ("USB\\VID_046D&PID_C52B\\6&xyz", ("046d", "c52b")),
        ("USB\\ROOT_HUB30\\4&internal", (None, None)),
        (None, (None, None)),
        (1234, (None, None)),
    ],
)
def test_vid_pid(device_id, expected):
    assert usb._vid_pid(device_id) == expected


@pytest.mark.parametrize(
    "value, expected",
    [("0x8087", "8087"), ("0x046d  (Logitech)", "046d"), ("8087", "8087"), ("", None), ("none", None)],
)
def test_hex_id(value, expected):
    assert usb._hex_id(value) == expected


# --------------------------------------------------------------------------- #
# Windows / CIM
# --------------------------------------------------------------------------- #

def test_windows_parses_usb(monkeypatch):
    rows = [
        {
            "Name": "USB Composite Device",
            "Manufacturer": "(Standard USB Host Controller)",
            "PNPDeviceID": "USB\\VID_8087&PID_0024\\5&abc",
        },
        {
            "Name": "USB Root Hub",
            "Manufacturer": "Unknown",  # placeholder -> scrubbed
            "PNPDeviceID": "USB\\ROOT_HUB30\\4&internal",  # no VID/PID
        },
    ]
    monkeypatch.setattr(usb._smbios, "run_cim", lambda *a, **k: rows)

    sec = usb._collect_windows()

    assert sec.name == "usb"
    assert sec.status is Status.OK
    assert sec.data["count"] == 2
    d0 = sec.data["devices"][0]
    assert d0["vendor_id"] == "8087"
    assert d0["product_id"] == "0024"
    d1 = sec.data["devices"][1]
    assert "vendor_id" not in d1  # root hub has no VID/PID
    assert "manufacturer" not in d1  # placeholder scrubbed


def test_windows_command_failure_is_unavailable(monkeypatch):
    monkeypatch.setattr(usb._smbios, "run_cim", lambda *a, **k: None)
    sec = usb._collect_windows()
    assert sec.status is Status.UNAVAILABLE
    assert sec.status is not Status.ERROR


# --------------------------------------------------------------------------- #
# Linux / lsusb + sysfs fallback
# --------------------------------------------------------------------------- #

_LSUSB = """Bus 002 Device 001: ID 1d6b:0003 Linux Foundation 3.0 root hub
Bus 001 Device 003: ID 8087:0024 Intel Corp. Integrated Rate Matching Hub
Bus 001 Device 002: ID 046d:c52b Logitech, Inc. Unifying Receiver
"""


def test_linux_lsusb_parse():
    devices = usb._parse_lsusb(_LSUSB)
    assert len(devices) == 3
    assert devices[1] == {"name": "Intel Corp. Integrated Rate Matching Hub",
                          "vendor_id": "8087", "product_id": "0024"}


def test_linux_prefers_lsusb(monkeypatch):
    monkeypatch.setattr(usb, "current_os", lambda: "linux")
    monkeypatch.setattr(usb, "run_command", lambda *a, **k: _LSUSB)
    sec = usb.collect()
    assert sec.status is Status.OK
    assert sec.data["count"] == 3


def test_linux_sysfs_fallback(tmp_path):
    # Build a fake /sys/bus/usb/devices: one real device + one hub (no idVendor).
    dev = tmp_path / "1-1"
    dev.mkdir()
    (dev / "idVendor").write_text("046d\n")
    (dev / "idProduct").write_text("c52b\n")
    (dev / "product").write_text("USB Receiver\n")
    (dev / "manufacturer").write_text("Logitech\n")
    hub = tmp_path / "usb1"  # root hub: no idVendor/idProduct -> dropped
    hub.mkdir()

    devices = usb._parse_sysfs_usb(str(tmp_path))
    assert devices == [{
        "name": "USB Receiver", "manufacturer": "Logitech",
        "vendor_id": "046d", "product_id": "c52b",
    }]


def test_linux_sysfs_skips_interface_nodes(monkeypatch, tmp_path):
    # Interface nodes carry a ':' in their name and no idVendor; the ':' guard
    # must skip them before any file read (verified portably — NTFS forbids ':'
    # in filenames, so we drive listdir directly).
    dev = tmp_path / "2-1"
    dev.mkdir()
    (dev / "idVendor").write_text("8087\n")
    (dev / "idProduct").write_text("0024\n")
    monkeypatch.setattr(usb.os, "listdir", lambda _root: ["2-1", "2-1:1.0"])

    devices = usb._parse_sysfs_usb(str(tmp_path))
    assert [d["vendor_id"] for d in devices] == ["8087"]


def test_linux_unavailable_when_nothing(monkeypatch):
    monkeypatch.setattr(usb, "current_os", lambda: "linux")
    monkeypatch.setattr(usb, "run_command", lambda *a, **k: None)
    monkeypatch.setattr(usb, "_parse_sysfs_usb", lambda *a, **k: [])
    sec = usb.collect()
    assert sec.status is Status.UNAVAILABLE
    assert sec.status is not Status.ERROR


# --------------------------------------------------------------------------- #
# macOS / system_profiler
# --------------------------------------------------------------------------- #

_MAC_USB = """USB:

    USB 3.0 Bus:

      Host Controller Driver: AppleUSBXHCITR

        Unifying Receiver:

          Product ID: 0xc52b
          Vendor ID: 0x046d  (Logitech Inc.)
          Manufacturer: Logitech

        Apple Internal Keyboard:

          Product ID: 0x027e
          Vendor ID: 0x05ac
"""


def test_macos_parse(monkeypatch):
    monkeypatch.setattr(usb, "current_os", lambda: "macos")
    monkeypatch.setattr(usb, "run_command", lambda *a, **k: _MAC_USB)

    sec = usb.collect()

    assert sec.status is Status.OK
    assert sec.data["count"] == 2
    d0 = sec.data["devices"][0]
    assert d0["name"] == "Unifying Receiver"
    assert d0["vendor_id"] == "046d"
    assert d0["product_id"] == "c52b"
    assert d0["manufacturer"] == "Logitech"


# --------------------------------------------------------------------------- #
# unsupported + never-raises
# --------------------------------------------------------------------------- #

def test_unsupported_os(monkeypatch):
    monkeypatch.setattr(usb, "current_os", lambda: "other")
    sec = usb.collect()
    assert sec.status is Status.UNSUPPORTED


def test_collect_never_raises_on_real_host():
    sec = usb.collect()
    assert sec.name == "usb"
    assert sec.status is not Status.ERROR


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
