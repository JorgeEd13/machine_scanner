"""Tests for the physical storage-drives collector.

Offline and hardware-agnostic: each OS path is driven through a stubbed
``run_command`` / ``_smbios.run_cim``, a tmp ``/sys/block`` tree, and a canned
``lsblk -J`` JSON blob. Covers bus/media mapping, the SMART root-gating degrade,
the lsblk fallback to sysfs, empty-result UNAVAILABLE, and never-raises.
"""

import json

import pytest

from machine_scanner.collectors import storage_devices as sd
from machine_scanner.core.models import Status

# --------------------------------------------------------------------------- #
# Unit helpers
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "value, expected",
    [
        (500107862016, 465.76),
        ("500107862016", 465.76),
        (0, None),
        ("", None),
        ("not-a-number", None),
        (True, None),
        (None, None),
    ],
)
def test_bytes_to_gb(value, expected):
    assert sd._bytes_to_gb(value) == expected


@pytest.mark.parametrize(
    "code, table, expected",
    [
        (4, sd._WIN_MEDIA, "SSD"),
        (3, sd._WIN_MEDIA, "HDD"),
        (0, sd._WIN_MEDIA, None),
        (17, sd._WIN_BUS, "NVMe"),
        (11, sd._WIN_BUS, "SATA"),
        (7, sd._WIN_BUS, "USB"),
        (0, sd._WIN_HEALTH, "healthy"),
        (True, sd._WIN_HEALTH, None),  # bool is not a real code
        (None, sd._WIN_BUS, None),
    ],
)
def test_label_from_code(code, table, expected):
    assert sd._label_from_code(code, table) == expected


@pytest.mark.parametrize(
    "rota, expected",
    [("1", "HDD"), ("0", "SSD"), (1, "HDD"), (0, "SSD"), ("True", "HDD"), (None, None)],
)
def test_media_from_rota(rota, expected):
    assert sd._media_from_rota(rota) == expected


@pytest.mark.parametrize(
    "tran, expected",
    [("nvme", "NVMe"), ("sata", "SATA"), ("usb", "USB"), ("weird", "WEIRD"), (None, None)],
)
def test_bus_label(tran, expected):
    assert sd._bus_label(tran) == expected


# --------------------------------------------------------------------------- #
# Windows — MSFT_PhysicalDisk
# --------------------------------------------------------------------------- #

_MSFT = [
    {
        "DeviceId": "0",
        "FriendlyName": "Samsung SSD 970 EVO 500GB",
        "Model": "Samsung SSD 970 EVO 500GB",
        "SerialNumber": "S4EVNF0M123456",
        "FirmwareVersion": "2B2QEXE7",
        "MediaType": 4,   # SSD
        "BusType": 17,    # NVMe
        "Size": 500107862016,
        "HealthStatus": 0,
        "SpindleSpeed": 0,
    },
    {
        "DeviceId": "1",
        "FriendlyName": "ST1000DM010-2EP102",
        "Model": "ST1000DM010-2EP102",
        "SerialNumber": "Z9A1BCDE",
        "FirmwareVersion": "CC43",
        "MediaType": 3,   # HDD
        "BusType": 11,    # SATA
        "Size": 1000204886016,
        "HealthStatus": 0,
        "SpindleSpeed": 7200,
    },
]


def test_windows_parses_drives_and_smart_ok(monkeypatch):
    def fake_cim(script, *a, **k):
        if "MSFT_PhysicalDisk" in script:
            return _MSFT
        if "FailurePredictStatus" in script:
            return [{"InstanceName": "x", "PredictFailure": False}]
        return None

    monkeypatch.setattr(sd._smbios, "run_cim", fake_cim)

    sec = sd._collect_windows()

    assert sec.name == "storage_devices"
    assert sec.status is Status.OK
    assert sec.data["count"] == 2
    nvme = sec.data["drives"][0]
    assert nvme["bus"] == "NVMe"
    assert nvme["media"] == "SSD"
    assert nvme["serial"] == "S4EVNF0M123456"
    assert nvme["firmware"] == "2B2QEXE7"
    assert nvme["health"] == "healthy"
    assert "rpm" not in nvme  # SSD spindle 0 -> dropped
    hdd = sec.data["drives"][1]
    assert hdd["media"] == "HDD"
    assert hdd["rpm"] == 7200
    assert any("no imminent failure" in n for n in sec.notes)


def test_windows_smart_needs_admin_is_partial(monkeypatch):
    def fake_cim(script, *a, **k):
        if "MSFT_PhysicalDisk" in script:
            return _MSFT
        return None  # SMART query blocked

    monkeypatch.setattr(sd._smbios, "run_cim", fake_cim)
    monkeypatch.setattr(sd, "is_admin", lambda: False)

    sec = sd._collect_windows()

    assert sec.status is Status.PARTIAL
    assert sec.status is not Status.ERROR
    assert any("administrator" in n for n in sec.notes)
    # Drive identity is still fully reported despite the SMART gate.
    assert sec.data["drives"][0]["model"].startswith("Samsung")


def test_windows_smart_predicts_failure(monkeypatch):
    def fake_cim(script, *a, **k):
        if "MSFT_PhysicalDisk" in script:
            return _MSFT
        return [{"InstanceName": "x", "PredictFailure": True}]

    monkeypatch.setattr(sd._smbios, "run_cim", fake_cim)
    sec = sd._collect_windows()
    assert any("predicts imminent failure" in n for n in sec.notes)


def test_windows_falls_back_to_win32_diskdrive(monkeypatch):
    win32 = [{
        "Model": "WDC WD10EZEX-08WN4A0",
        "SerialNumber": "WD-WCC6Y1234567",
        "FirmwareRevision": "01.01A01",
        "Size": 1000202273280,
        "InterfaceType": "IDE",
    }]

    def fake_cim(script, *a, **k):
        if "MSFT_PhysicalDisk" in script:
            return None  # storage provider absent
        if "Win32_DiskDrive" in script:
            return win32
        return None

    monkeypatch.setattr(sd._smbios, "run_cim", fake_cim)
    monkeypatch.setattr(sd, "is_admin", lambda: True)

    sec = sd._collect_windows()

    assert sec.data["count"] == 1
    drive = sec.data["drives"][0]
    assert drive["model"].startswith("WDC")
    assert drive["bus"] == "IDE"
    assert "media" not in drive  # Win32_DiskDrive has no media type
    assert any("Win32_DiskDrive" in n for n in sec.notes)


def test_windows_total_failure_is_unavailable(monkeypatch):
    monkeypatch.setattr(sd._smbios, "run_cim", lambda *a, **k: None)
    sec = sd._collect_windows()
    assert sec.status is Status.UNAVAILABLE
    assert sec.status is not Status.ERROR


# --------------------------------------------------------------------------- #
# Linux — lsblk JSON
# --------------------------------------------------------------------------- #

_LSBLK = json.dumps({
    "blockdevices": [
        {
            "name": "nvme0n1", "type": "disk", "model": "KXG60ZNV512G",
            "serial": "Z9NF70...", "rev": "AGGA4104", "size": 512110190592,
            "rota": "0", "tran": "nvme",
        },
        {
            "name": "sda", "type": "disk", "model": "ST2000DM008-2FR102",
            "serial": "ZFL1ABCD", "rev": "0001", "size": 2000398934016,
            "rota": "1", "tran": "sata",
        },
        {
            "name": "sr0", "type": "rom", "model": "DVD-RW", "size": 1073741312,
            "rota": "1", "tran": "sata",
        },
        {
            "name": "loop0", "type": "loop", "size": 12345678, "rota": "0",
        },
    ]
})


def test_linux_lsblk_parse_filters_and_maps():
    drives = sd._parse_lsblk(_LSBLK)
    names = [d["name"] for d in drives]
    assert names == ["nvme0n1", "sda"]  # rom + loop dropped
    nvme = drives[0]
    assert nvme["bus"] == "NVMe"
    assert nvme["media"] == "SSD"
    assert nvme["firmware"] == "AGGA4104"
    assert nvme["size_gb"] == round(512110190592 / 1024 ** 3, 2)
    assert drives[1]["media"] == "HDD"


def test_linux_collect_smart_root_gated_is_partial(monkeypatch):
    def fake_run(args, *a, **k):
        if args[0] == "lsblk":
            return _LSBLK
        if args[0] == "smartctl":
            return None  # not root / not installed
        return None

    monkeypatch.setattr(sd, "run_command", fake_run)
    monkeypatch.setattr(sd, "is_admin", lambda: False)

    sec = sd._collect_linux()

    assert sec.status is Status.PARTIAL
    assert sec.status is not Status.ERROR
    assert sec.data["count"] == 2
    assert any("root" in n for n in sec.notes)


def test_linux_collect_smart_passed(monkeypatch):
    smart_json = json.dumps({"smart_status": {"passed": True}})

    def fake_run(args, *a, **k):
        if args[0] == "lsblk":
            return _LSBLK
        if args[0] == "smartctl":
            return smart_json
        return None

    monkeypatch.setattr(sd, "run_command", fake_run)

    sec = sd._collect_linux()

    assert sec.status is Status.OK
    assert sec.data["drives"][0]["health"] == "passed"


# --------------------------------------------------------------------------- #
# Linux — /sys/block fallback (tmp tree)
# --------------------------------------------------------------------------- #

def _make_sysfs(tmp_path):
    block = tmp_path / "block"
    nvme = block / "nvme0n1"
    (nvme / "device").mkdir(parents=True)
    (nvme / "queue").mkdir()
    (nvme / "size").write_text("1000215216\n")  # 512-byte sectors
    (nvme / "queue" / "rotational").write_text("0\n")
    (nvme / "device" / "model").write_text("Force MP510\n")
    (nvme / "device" / "serial").write_text("1924812340\n")
    (nvme / "device" / "firmware_rev").write_text("ECFM12.3\n")
    # noise that must be filtered out
    loop = block / "loop0"
    (loop / "queue").mkdir(parents=True)
    (loop / "size").write_text("0\n")
    return block


def test_linux_sysfs_fallback(tmp_path):
    block = _make_sysfs(tmp_path)
    drives = sd._collect_linux_sysfs(str(block))
    assert len(drives) == 1
    drive = drives[0]
    assert drive["name"] == "nvme0n1"
    assert drive["model"] == "Force MP510"
    assert drive["bus"] == "NVMe"
    assert drive["media"] == "SSD"
    assert drive["firmware"] == "ECFM12.3"
    assert drive["size_gb"] == round(1000215216 * 512 / 1024 ** 3, 2)


def test_linux_lsblk_missing_uses_sysfs(monkeypatch, tmp_path):
    block = _make_sysfs(tmp_path)
    monkeypatch.setattr(sd, "_SYS_BLOCK", str(block))

    def fake_run(args, *a, **k):
        if args[0] == "lsblk":
            return  # lsblk absent
        return  # smartctl absent too

    monkeypatch.setattr(sd, "run_command", fake_run)
    monkeypatch.setattr(sd, "is_admin", lambda: False)

    sec = sd._collect_linux()

    assert sec.data["count"] == 1
    assert any("/sys/block" in n for n in sec.notes)


def test_linux_no_devices_is_unavailable(monkeypatch):
    monkeypatch.setattr(sd, "run_command", lambda *a, **k: None)
    monkeypatch.setattr(sd, "_collect_linux_sysfs", lambda *a, **k: [])
    sec = sd._collect_linux()
    assert sec.status is Status.UNAVAILABLE
    assert sec.status is not Status.ERROR


# --------------------------------------------------------------------------- #
# macOS — diskutil info -all
# --------------------------------------------------------------------------- #

_DISKUTIL = """   Device Identifier:         disk0
   Device / Media Name:       APPLE SSD AP0512N

   Virtual:                   No
   Protocol:                  Apple Fabric
   SMART Status:              Verified

   Disk Size:                 500.3 GB (500277790720 Bytes)
   Solid State:               Yes

**********

   Device Identifier:         disk1
   Device / Media Name:       Disk Image

   Virtual:                   Yes
   Disk Size:                 10.0 GB (10000000000 Bytes)

**********
"""


def test_macos_parse_keeps_physical_drops_virtual():
    drives = sd._parse_diskutil(_DISKUTIL)
    assert len(drives) == 1
    drive = drives[0]
    assert drive["model"] == "APPLE SSD AP0512N"
    assert drive["media"] == "SSD"
    assert drive["bus"] == "Apple Fabric"
    assert drive["health"] == "Verified"
    assert drive["size_gb"] == round(500277790720 / 1024 ** 3, 2)


def test_macos_collect(monkeypatch):
    monkeypatch.setattr(sd, "current_os", lambda: "macos")
    monkeypatch.setattr(sd, "run_command", lambda *a, **k: _DISKUTIL)
    sec = sd.collect()
    assert sec.status is Status.OK
    assert sec.data["count"] == 1


# --------------------------------------------------------------------------- #
# unsupported + never-raises
# --------------------------------------------------------------------------- #

def test_unsupported_os(monkeypatch):
    monkeypatch.setattr(sd, "current_os", lambda: "other")
    sec = sd.collect()
    assert sec.status is Status.UNSUPPORTED


def test_collect_never_raises_on_real_host():
    sec = sd.collect()
    assert sec.name == "storage_devices"
    assert sec.status is not Status.ERROR


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
