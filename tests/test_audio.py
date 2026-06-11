"""Tests for the audio-devices collector."""

import pytest

from machine_scanner.collectors import audio as a
from machine_scanner.core.models import Status


# --------------------------------------------------------------------------- #
# Windows / CIM
# --------------------------------------------------------------------------- #

def test_windows_parse(monkeypatch):
    rows = [
        {"Name": "Realtek High Definition Audio", "Manufacturer": "Realtek"},
        {"Name": "Intel(R) Display Audio", "Manufacturer": "Intel"},
    ]
    monkeypatch.setattr(a._smbios, "run_cim", lambda *a, **k: rows)
    sec = a._collect_windows()
    assert sec.name == "audio"
    assert sec.status is Status.OK
    assert sec.data["count"] == 2
    assert sec.data["devices"][0]["name"] == "Realtek High Definition Audio"


def test_windows_failure_is_unavailable(monkeypatch):
    monkeypatch.setattr(a._smbios, "run_cim", lambda *a, **k: None)
    sec = a._collect_windows()
    assert sec.status is Status.UNAVAILABLE
    assert sec.status is not Status.ERROR


# --------------------------------------------------------------------------- #
# Linux / /proc/asound/cards
# --------------------------------------------------------------------------- #

_ASOUND = """ 0 [PCH            ]: HDA-Intel - HDA Intel PCH
                      HDA Intel PCH at 0xf7d40000 irq 31
 1 [NVidia         ]: HDA-Intel - HDA NVidia
                      HDA NVidia at 0xf7080000 irq 17
"""


def test_linux_parse_asound():
    devices = a._parse_asound(_ASOUND)
    assert len(devices) == 2
    assert devices[0]["name"] == "HDA-Intel - HDA Intel PCH"
    assert devices[1]["name"] == "HDA-Intel - HDA NVidia"


def test_linux_reads_proc(tmp_path):
    cards = tmp_path / "cards"
    cards.write_text(_ASOUND)
    sec = a._collect_linux(str(cards))
    assert sec.status is Status.OK
    assert sec.data["count"] == 2


def test_linux_no_soundcards(tmp_path):
    cards = tmp_path / "cards"
    cards.write_text("--- no soundcards ---\n")
    sec = a._collect_linux(str(cards))
    assert sec.status is Status.UNAVAILABLE
    assert sec.status is not Status.ERROR


def test_linux_missing_file_is_unavailable():
    sec = a._collect_linux("/nonexistent/asound")
    assert sec.status is Status.UNAVAILABLE


# --------------------------------------------------------------------------- #
# macOS
# --------------------------------------------------------------------------- #

_MAC_AUDIO = """Audio:

    Devices:

        MacBook Pro Speakers:
          Default Output Device: Yes
        External Headphones:
          Manufacturer: Apple Inc.
"""


def test_macos_parse(monkeypatch):
    monkeypatch.setattr(a, "current_os", lambda: "macos")
    monkeypatch.setattr(a, "run_command", lambda *args, **k: _MAC_AUDIO)
    sec = a.collect()
    assert sec.status is Status.OK
    names = [d["name"] for d in sec.data["devices"]]
    assert "MacBook Pro Speakers" in names and "External Headphones" in names


# --------------------------------------------------------------------------- #
# unsupported + never-raises
# --------------------------------------------------------------------------- #

def test_unsupported_os(monkeypatch):
    monkeypatch.setattr(a, "current_os", lambda: "other")
    assert a.collect().status is Status.UNSUPPORTED


def test_collect_never_raises_on_real_host():
    sec = a.collect()
    assert sec.name == "audio"
    assert sec.status is not Status.ERROR


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
