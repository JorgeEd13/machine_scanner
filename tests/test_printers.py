"""Tests for the printers collector (offline — no spooler / CUPS touched)."""

import pytest

from machine_scanner.collectors import printers as p
from machine_scanner.core.models import Status

# --------------------------------------------------------------------------- #
# Windows / CIM
# --------------------------------------------------------------------------- #

def test_windows_parse(monkeypatch):
    rows = [
        {"Name": "Office LaserJet", "Default": True, "PortName": "192.168.0.20",
         "DriverName": "HP LJ", "Shared": False, "Network": True, "WorkOffline": False},
        {"Name": "Microsoft Print to PDF", "Default": False, "PortName": "PORTPROMPT:",
         "DriverName": "MS PDF", "Shared": False, "Network": False, "WorkOffline": False},
    ]
    monkeypatch.setattr(p._smbios, "run_cim", lambda *a, **k: rows)
    sec = p._collect_windows()
    assert sec.name == "printers"
    assert sec.status is Status.OK
    assert sec.data["count"] == 2
    first = sec.data["printers"][0]
    assert first["name"] == "Office LaserJet"
    assert first["default"] is True
    assert first["network"] is True
    # default=False must survive the None-drop (it is meaningful)
    assert sec.data["printers"][1]["default"] is False


def test_windows_empty_is_clean_unavailable(monkeypatch):
    monkeypatch.setattr(p._smbios, "run_cim", lambda *a, **k: [])
    sec = p._collect_windows()
    assert sec.status is Status.UNAVAILABLE
    assert sec.status is not Status.ERROR


def test_windows_query_failure_is_unavailable(monkeypatch):
    monkeypatch.setattr(p._smbios, "run_cim", lambda *a, **k: None)
    assert p._collect_windows().status is Status.UNAVAILABLE


# --------------------------------------------------------------------------- #
# Linux / lpstat
# --------------------------------------------------------------------------- #

_LPSTAT_P = """printer Office_LaserJet is idle.  enabled since Mon 01 Jan 2026
printer Old_Inkjet disabled since Tue 02 Jan 2026 -
\treason unknown
printer PDF_Queue now printing PDF_Queue-42.
"""
_LPSTAT_D = "system default destination: Office_LaserJet\n"


def test_linux_parse(monkeypatch):
    def fake_run(args, *a, **k):
        return _LPSTAT_P if args[:2] == ["lpstat", "-p"] else _LPSTAT_D
    monkeypatch.setattr(p, "run_command", fake_run)
    sec = p._collect_linux()
    assert sec.status is Status.OK
    assert sec.data["count"] == 3
    by_name = {d["name"]: d for d in sec.data["printers"]}
    assert by_name["Office_LaserJet"]["status"] == "idle"
    assert by_name["Office_LaserJet"]["default"] is True
    assert by_name["Old_Inkjet"]["status"] == "disabled"
    assert by_name["PDF_Queue"]["status"] == "printing"
    assert by_name["PDF_Queue"]["default"] is False


def test_linux_no_cups_is_clean_unavailable(monkeypatch):
    monkeypatch.setattr(p, "run_command", lambda *a, **k: None)
    sec = p._collect_linux()
    assert sec.status is Status.UNAVAILABLE
    assert sec.status is not Status.ERROR
    assert any("CUPS" in n or "lpstat" in n for n in sec.notes)


def test_linux_no_destinations_is_unavailable(monkeypatch):
    monkeypatch.setattr(p, "run_command", lambda *a, **k: "")
    sec = p._collect_linux()
    assert sec.status is Status.UNAVAILABLE


# --------------------------------------------------------------------------- #
# macOS
# --------------------------------------------------------------------------- #

_MAC_PRINTERS = """Printers:

    HP LaserJet:
      Status: Idle
      Default: Yes
      Driver Version: 1.2

    Brother MFC:
      Status: Idle
      Default: No
"""


def test_macos_parse(monkeypatch):
    monkeypatch.setattr(p, "current_os", lambda: "macos")
    monkeypatch.setattr(p, "run_command", lambda *a, **k: _MAC_PRINTERS)
    sec = p.collect()
    assert sec.status is Status.OK
    by_name = {d["name"]: d for d in sec.data["printers"]}
    assert by_name["HP LaserJet"]["default"] is True
    assert by_name["HP LaserJet"]["status"] == "idle"
    assert by_name["Brother MFC"]["default"] is False


# --------------------------------------------------------------------------- #
# unsupported + never-raises
# --------------------------------------------------------------------------- #

def test_unsupported_os(monkeypatch):
    monkeypatch.setattr(p, "current_os", lambda: "other")
    assert p.collect().status is Status.UNSUPPORTED


def test_collect_never_raises_on_real_host():
    sec = p.collect()
    assert sec.name == "printers"
    assert sec.status is not Status.ERROR


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
