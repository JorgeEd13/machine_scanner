"""Tests for the input-devices collector."""

import pytest

from machine_scanner.collectors import input_devices as inp
from machine_scanner.core.models import Status

# --------------------------------------------------------------------------- #
# Windows / CIM
# --------------------------------------------------------------------------- #

def test_windows_combines_keyboard_and_pointer(monkeypatch):
    rows = [
        {"kind": "keyboard", "Name": "Standard PS/2 Keyboard", "Manufacturer": "(Standard keyboards)"},
        {"kind": "pointing", "Name": "HID-compliant mouse", "Manufacturer": "Microsoft"},
    ]
    monkeypatch.setattr(inp._smbios, "run_cim", lambda *a, **k: rows)

    sec = inp._collect_windows()

    assert sec.name == "input"
    assert sec.status is Status.OK
    assert sec.data["count"] == 2
    assert sec.data["devices"][0]["kind"] == "keyboard"
    assert sec.data["devices"][1]["name"] == "HID-compliant mouse"


def test_windows_failure_is_unavailable(monkeypatch):
    monkeypatch.setattr(inp._smbios, "run_cim", lambda *a, **k: None)
    sec = inp._collect_windows()
    assert sec.status is Status.UNAVAILABLE
    assert sec.status is not Status.ERROR


# --------------------------------------------------------------------------- #
# Linux / /proc/bus/input/devices
# --------------------------------------------------------------------------- #

_PROC_INPUT = '''I: Bus=0019 Vendor=0000 Product=0001 Version=0000
N: Name="Power Button"
H: Handlers=kbd event0
B: EV=3

I: Bus=0003 Vendor=046d Product=c52b Version=0111
N: Name="Logitech USB Receiver"
H: Handlers=mouse0 event3
B: EV=17

I: Bus=0011 Vendor=0001 Product=0001 Version=ab41
N: Name="AT Translated Set 2 keyboard"
H: Handlers=sysrq kbd event4
B: EV=120013

I: Bus=0003 Vendor=0bda Product=5520 Version=1234
N: Name="Integrated Webcam"
H: Handlers=
B: EV=3
'''


def test_linux_parse_classifies_and_drops_non_input():
    devices = inp._parse_proc_input(_PROC_INPUT)
    kinds = [(d["kind"], d["name"]) for d in devices]
    assert ("keyboard", "Power Button") in kinds
    assert ("pointing", "Logitech USB Receiver") in kinds
    assert ("keyboard", "AT Translated Set 2 keyboard") in kinds
    # the webcam has no kbd/mouse handler -> dropped
    assert all("Webcam" not in d["name"] for d in devices)


def test_linux_no_proc_is_unavailable():
    sec = inp._collect_linux("/nonexistent/input")
    assert sec.status is Status.UNAVAILABLE
    assert sec.status is not Status.ERROR


# --------------------------------------------------------------------------- #
# macOS / unsupported + never-raises
# --------------------------------------------------------------------------- #

def test_macos_is_unsupported_with_pointer(monkeypatch):
    monkeypatch.setattr(inp, "current_os", lambda: "macos")
    sec = inp.collect()
    assert sec.status is Status.UNSUPPORTED
    assert any("usb" in n for n in sec.notes)


def test_unsupported_os(monkeypatch):
    monkeypatch.setattr(inp, "current_os", lambda: "other")
    assert inp.collect().status is Status.UNSUPPORTED


def test_collect_never_raises_on_real_host():
    sec = inp.collect()
    assert sec.name == "input"
    assert sec.status is not Status.ERROR


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
