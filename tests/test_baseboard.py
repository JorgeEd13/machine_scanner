"""Tests for the motherboard / BIOS collector.

Fully offline and hardware-agnostic: every OS path is driven through a stubbed
``run_command`` / DMI directory, so the same suite runs identically on any CI
runner. The contract under test: parse real-looking firmware output, scrub
vendor placeholders, surface a privilege note instead of failing, and *never*
raise for an expected-absent case.
"""

import json

import pytest

from machine_scanner.collectors import baseboard
from machine_scanner.core.models import Status

# --------------------------------------------------------------------------- #
# placeholder scrubbing
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("ASUSTeK COMPUTER INC.", "ASUSTeK COMPUTER INC."),
        ("  Trimmed  ", "Trimmed"),
        ("To Be Filled By O.E.M.", None),
        ("Default string", None),
        ("System Serial Number", None),
        ("", None),
        ("None", None),
        ("FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF", None),
        (None, None),
    ],
)
def test_clean_scrubs_placeholders(raw, expected):
    assert baseboard._clean(raw) == expected


# --------------------------------------------------------------------------- #
# Windows / CIM JSON path
# --------------------------------------------------------------------------- #

_WIN_JSON = json.dumps(
    {
        "bios_vendor": "American Megatrends Inc.",
        "bios_version": "1402",
        "bios_release_date": "2021-03-12",
        "bios_serial": "System Serial Number",  # placeholder -> dropped
        "baseboard_manufacturer": "ASUSTeK COMPUTER INC.",
        "baseboard_product": "PRIME B450M-A",
        "baseboard_version": "Rev X.0x",
        "baseboard_serial": "180000000000000",
        "system_manufacturer": "ASUS",
        "system_product": "All Series",
        "system_version": "System Version",  # placeholder -> dropped
        "system_serial": "ABC123XYZ",
        "system_uuid": "1f2e3d4c-5b6a-7980-1122-334455667788",
    }
)


def test_windows_parses_and_scrubs(monkeypatch):
    monkeypatch.setattr(baseboard, "current_os", lambda: "windows")
    monkeypatch.setattr(baseboard, "is_admin", lambda: True)
    monkeypatch.setattr(baseboard, "run_command", lambda *a, **k: _WIN_JSON)

    sec = baseboard.collect()

    assert sec.status is Status.OK
    assert sec.data["baseboard_product"] == "PRIME B450M-A"
    assert sec.data["system_serial"] == "ABC123XYZ"
    # Placeholder fields are absent entirely, not blank.
    assert "bios_serial" not in sec.data
    assert "system_version" not in sec.data


def test_windows_command_failure_is_unavailable_not_error(monkeypatch):
    monkeypatch.setattr(baseboard, "current_os", lambda: "windows")
    monkeypatch.setattr(baseboard, "run_command", lambda *a, **k: None)

    sec = baseboard.collect()

    assert sec.status is Status.UNAVAILABLE
    assert sec.status is not Status.ERROR
    assert sec.notes


def test_windows_garbage_output_is_unavailable(monkeypatch):
    monkeypatch.setattr(baseboard, "current_os", lambda: "windows")
    monkeypatch.setattr(baseboard, "run_command", lambda *a, **k: "not json {{{")

    sec = baseboard.collect()

    assert sec.status is Status.UNAVAILABLE


# --------------------------------------------------------------------------- #
# Linux / sysfs DMI path
# --------------------------------------------------------------------------- #

def _write_dmi(directory, **files):
    for name, value in files.items():
        (directory / name).write_text(value, encoding="utf-8")


def test_linux_reads_sysfs_dmi(monkeypatch, tmp_path):
    _write_dmi(
        tmp_path,
        sys_vendor="LENOVO",
        product_name="20XYZ",
        board_vendor="LENOVO",
        board_name="3A2B",
        bios_vendor="LENOVO",
        bios_version="N3HET49W",
        bios_date="06/01/2023",
        product_serial="PF1234567",
        product_uuid="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        board_serial="L1HF000000",
    )
    monkeypatch.setattr(baseboard, "is_admin", lambda: True)

    sec = baseboard._collect_linux(str(tmp_path))

    assert sec.status is Status.OK
    assert sec.data["system_manufacturer"] == "LENOVO"
    assert sec.data["bios_release_date"] == "06/01/2023"
    assert sec.data["system_serial"] == "PF1234567"


def test_linux_missing_serial_degrades_to_partial(monkeypatch, tmp_path):
    # Identity present, but the root-only serial/uuid files are absent -> the
    # collector should still succeed, flagged PARTIAL with an elevation note.
    _write_dmi(
        tmp_path,
        sys_vendor="LENOVO",
        product_name="20XYZ",
        board_vendor="LENOVO",
        board_name="3A2B",
    )
    monkeypatch.setattr(baseboard, "is_admin", lambda: False)

    sec = baseboard._collect_linux(str(tmp_path))

    assert sec.status is Status.PARTIAL
    assert "system_serial" not in sec.data
    assert any("elevation" in note for note in sec.notes)


def test_linux_no_dmi_table_is_unavailable(tmp_path):
    sec = baseboard._collect_linux(str(tmp_path / "does-not-exist"))
    assert sec.status is Status.UNAVAILABLE
    assert sec.status is not Status.ERROR


# --------------------------------------------------------------------------- #
# macOS / system_profiler path
# --------------------------------------------------------------------------- #

_MAC_OUTPUT = """Hardware:

    Hardware Overview:

      Model Name: MacBook Pro
      Model Identifier: MacBookPro18,3
      Serial Number (system): C02ABCDEFGH
      Hardware UUID: 12345678-90AB-CDEF-1234-567890ABCDEF
      Boot ROM Version: 8419.80.7
"""


def test_macos_parses_system_profiler(monkeypatch):
    monkeypatch.setattr(baseboard, "current_os", lambda: "macos")
    monkeypatch.setattr(baseboard, "is_admin", lambda: True)
    monkeypatch.setattr(baseboard, "run_command", lambda *a, **k: _MAC_OUTPUT)

    sec = baseboard.collect()

    assert sec.status is Status.OK
    assert sec.data["system_product"] == "MacBook Pro"
    assert sec.data["system_serial"] == "C02ABCDEFGH"
    assert sec.data["system_manufacturer"] == "Apple"  # synthesized default


# --------------------------------------------------------------------------- #
# unsupported OS + the universal "never raises" guarantee
# --------------------------------------------------------------------------- #

def test_unsupported_os(monkeypatch):
    monkeypatch.setattr(baseboard, "current_os", lambda: "other")
    sec = baseboard.collect()
    assert sec.status is Status.UNSUPPORTED
    assert sec.status is not Status.ERROR


def test_collect_never_raises_on_real_host():
    # Whatever this CI runner actually is, the live collector must return a
    # Section and never raise.
    sec = baseboard.collect()
    assert sec.name == "baseboard"
    assert sec.status is not Status.ERROR


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
