"""Tests for the battery collector.

The headline case is *absent* (a desktop): it must degrade to UNAVAILABLE with
``present: False`` and never ERROR.
"""

import pytest

from machine_scanner.collectors import battery as b
from machine_scanner.core.models import Status


# --------------------------------------------------------------------------- #
# Windows / Win32_Battery
# --------------------------------------------------------------------------- #

def test_windows_with_battery(monkeypatch):
    rows = [{
        "Name": "DELL 0WND3 battery",
        "EstimatedChargeRemaining": 87,
        "BatteryStatus": 2,        # on AC
        "Chemistry": 6,            # lithium-ion
        "EstimatedRunTime": 71582788,  # "unknown" sentinel -> dropped
    }]
    monkeypatch.setattr(b._smbios, "run_cim", lambda *a, **k: rows)

    sec = b._collect_windows()

    assert sec.name == "battery"
    assert sec.status is Status.OK
    assert sec.data["present"] is True
    assert sec.data["charge_percent"] == 87
    assert sec.data["status"] == "on AC"
    assert sec.data["chemistry"] == "lithium-ion"
    assert "runtime_minutes" not in sec.data  # sentinel scrubbed


def test_windows_no_battery_is_absent(monkeypatch):
    monkeypatch.setattr(b._smbios, "run_cim", lambda *a, **k: [])
    sec = b._collect_windows()
    assert sec.status is Status.UNAVAILABLE
    assert sec.data["present"] is False
    assert sec.status is not Status.ERROR


def test_windows_query_failure(monkeypatch):
    monkeypatch.setattr(b._smbios, "run_cim", lambda *a, **k: None)
    sec = b._collect_windows()
    assert sec.status is Status.UNAVAILABLE


# --------------------------------------------------------------------------- #
# Linux / /sys/class/power_supply
# --------------------------------------------------------------------------- #

def test_linux_battery_with_health(tmp_path):
    bat = tmp_path / "BAT0"
    bat.mkdir()
    (bat / "capacity").write_text("87\n")
    (bat / "status").write_text("Discharging\n")
    (bat / "energy_full").write_text("45000000\n")
    (bat / "energy_full_design").write_text("50000000\n")
    (bat / "manufacturer").write_text("Sony\n")
    (bat / "model_name").write_text("DELL 0WND3\n")
    (bat / "technology").write_text("Li-ion\n")

    sec = b._collect_linux(str(tmp_path))

    assert sec.status is Status.OK
    assert sec.data["charge_percent"] == 87
    assert sec.data["status"] == "discharging"
    assert sec.data["health_percent"] == 90.0  # 45/50
    assert sec.data["manufacturer"] == "Sony"


def test_linux_no_battery_is_absent(tmp_path):
    sec = b._collect_linux(str(tmp_path))  # empty dir, no BAT*
    assert sec.status is Status.UNAVAILABLE
    assert sec.data["present"] is False
    assert sec.status is not Status.ERROR


# --------------------------------------------------------------------------- #
# macOS / SPPowerDataType
# --------------------------------------------------------------------------- #

_MAC_POWER = """Power:

    Battery Information:

      Charge Information:
          State of Charge (%): 92
          Charge Remaining (mAh): 5800
      Health Information:
          Cycle Count: 142
          Condition: Normal
"""

_MAC_DESKTOP = """Power:

    AC Power:
          Current Power Source: Yes
"""


def test_macos_with_battery(monkeypatch):
    monkeypatch.setattr(b, "current_os", lambda: "macos")
    monkeypatch.setattr(b, "run_command", lambda *a, **k: _MAC_POWER)
    sec = b.collect()
    assert sec.status is Status.OK
    assert sec.data["charge_percent"] == 92
    assert sec.data["cycle_count"] == 142
    assert sec.data["condition"] == "Normal"


def test_macos_desktop_is_absent(monkeypatch):
    monkeypatch.setattr(b, "current_os", lambda: "macos")
    monkeypatch.setattr(b, "run_command", lambda *a, **k: _MAC_DESKTOP)
    sec = b.collect()
    assert sec.status is Status.UNAVAILABLE
    assert sec.data["present"] is False


# --------------------------------------------------------------------------- #
# unsupported + never-raises
# --------------------------------------------------------------------------- #

def test_unsupported_os(monkeypatch):
    monkeypatch.setattr(b, "current_os", lambda: "other")
    assert b.collect().status is Status.UNSUPPORTED


def test_collect_never_raises_on_real_host():
    sec = b.collect()
    assert sec.name == "battery"
    assert sec.status is not Status.ERROR


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
