"""Tests for the multi-vendor GPU collector.

Offline and hardware-agnostic: each OS enumerator is driven through a stubbed
``run_command`` / ``_smbios.run_cim`` or a tmp sysfs tree. Covers vendor
classification, per-OS parsing, the nvidia-smi merge, and the never-raises
guarantee.
"""


import pytest

from machine_scanner.collectors import gpu
from machine_scanner.core.models import Status


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("NVIDIA Corporation", "NVIDIA"),
        ("Intel(R) HD Graphics 2500", "Intel"),
        ("Advanced Micro Devices, Inc. [AMD/ATI]", "AMD"),
        ("Radeon RX 580", "AMD"),
        ("Some Other Co", "Some Other Co"),
        ("To Be Filled By O.E.M.", None),
        (None, None),
    ],
)
def test_classify_vendor(raw, expected):
    assert gpu._classify_vendor(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [("1536 MB", 1536), ("2 GB", 2048), ("4096", 4096), ("", None), ("lots MB", None)],
)
def test_mb_from_text(raw, expected):
    assert gpu._mb_from_text(raw) == expected


# --------------------------------------------------------------------------- #
# Windows / CIM
# --------------------------------------------------------------------------- #

def test_windows_enumerate_parses_and_flags_capped_vram(monkeypatch):
    rows = [
        {
            "Name": "Intel(R) HD Graphics 2500",
            "AdapterCompatibility": "Intel Corporation",
            "AdapterRAM": 2147483648,  # 2 GiB
            "DriverVersion": "10.18.10.5161",
        },
        {
            "Name": "NVIDIA GeForce GTX 1080",
            "AdapterCompatibility": "NVIDIA",
            "AdapterRAM": 4294967295,  # 4 GiB-1 -> saturated 32-bit field
            "DriverVersion": "555.00",
        },
    ]
    monkeypatch.setattr(gpu._smbios, "run_cim", lambda *a, **k: rows)

    gpus, notes = gpu._enumerate_windows()

    assert gpus[0]["vendor"] == "Intel"
    assert gpus[0]["memory_total_mb"] == 2048
    assert gpus[1]["vendor"] == "NVIDIA"
    assert any("4 GiB" in n for n in notes)


def test_windows_enumerate_command_failure(monkeypatch):
    monkeypatch.setattr(gpu._smbios, "run_cim", lambda *a, **k: None)
    gpus, notes = gpu._enumerate_windows()
    assert gpus is None
    assert notes


# --------------------------------------------------------------------------- #
# Linux / lspci + sysfs fallback
# --------------------------------------------------------------------------- #

_LSPCI = (
    '00:02.0 "VGA compatible controller" "Intel Corporation" "HD Graphics 2500" -r09 "Lenovo" "Device 2113"\n'
    '01:00.0 "3D controller" "NVIDIA Corporation" "GP107M [GeForce GTX 1050]" -ra1 "" ""\n'
    '00:1f.0 "ISA bridge" "Intel Corporation" "Some Chipset" -r04 "" ""\n'
)


def test_linux_lspci_parse(monkeypatch):
    monkeypatch.setattr(gpu, "run_command", lambda *a, **k: _LSPCI)
    gpus, notes = gpu._enumerate_linux()
    # Only the two display devices, not the ISA bridge.
    assert len(gpus) == 2
    assert gpus[0]["vendor"] == "Intel"
    assert gpus[0]["name"] == "HD Graphics 2500"
    assert gpus[1]["vendor"] == "NVIDIA"
    assert notes == []


def test_linux_sysfs_fallback_when_no_lspci(monkeypatch, tmp_path):
    monkeypatch.setattr(gpu, "run_command", lambda *a, **k: None)
    card = tmp_path / "card0" / "device"
    card.mkdir(parents=True)
    (card / "vendor").write_text("0x8086\n", encoding="utf-8")
    # a connector node that must be ignored
    (tmp_path / "card0-eDP-1").mkdir()

    gpus, notes = gpu._enumerate_linux(str(tmp_path))

    assert gpus == [{"vendor": "Intel"}]
    assert any("lspci" in n for n in notes)


def test_linux_no_lspci_no_sysfs(monkeypatch, tmp_path):
    monkeypatch.setattr(gpu, "run_command", lambda *a, **k: None)
    gpus, _notes = gpu._enumerate_linux(str(tmp_path / "missing"))
    assert gpus is None


# --------------------------------------------------------------------------- #
# macOS
# --------------------------------------------------------------------------- #

_MAC_DISPLAYS = """Graphics/Displays:

    Intel Iris Pro:

      Chipset Model: Intel Iris Pro
      Type: GPU
      VRAM (Dynamic, Max): 1536 MB
      Vendor: Intel (0x8086)

    Radeon Pro 560:

      Chipset Model: AMD Radeon Pro 560
      Type: GPU
      VRAM (Total): 4 GB
      Vendor: AMD (0x1002)
"""


def test_macos_parse(monkeypatch):
    gpus = gpu._parse_macos(_MAC_DISPLAYS)
    assert len(gpus) == 2
    assert gpus[0]["name"] == "Intel Iris Pro"
    assert gpus[0]["vendor"] == "Intel"
    assert gpus[0]["memory_total_mb"] == 1536
    assert gpus[1]["vendor"] == "AMD"
    assert gpus[1]["memory_total_mb"] == 4096


# --------------------------------------------------------------------------- #
# collect() merge + status
# --------------------------------------------------------------------------- #

def test_collect_merges_nvidia_detail_over_generic(monkeypatch):
    monkeypatch.setattr(gpu, "current_os", lambda: "linux")
    monkeypatch.setattr(
        gpu, "_enumerate",
        lambda system: (
            [{"vendor": "Intel", "name": "HD 2500"}, {"vendor": "NVIDIA", "name": "generic"}],
            [],
        ),
    )
    monkeypatch.setattr(
        gpu, "_query_nvidia",
        lambda: [{"vendor": "NVIDIA", "name": "GTX 1050", "memory_total_mb": 4096.0}],
    )

    sec = gpu.collect()

    assert sec.status is Status.OK
    names = {g["name"] for g in sec.data["gpus"]}
    assert names == {"HD 2500", "GTX 1050"}  # generic NVIDIA replaced by detailed
    assert "generic" not in names


def test_collect_unsupported_os(monkeypatch):
    monkeypatch.setattr(gpu, "current_os", lambda: "other")
    monkeypatch.setattr(gpu, "_query_nvidia", lambda: None)
    sec = gpu.collect()
    assert sec.status is Status.UNSUPPORTED


def test_collect_no_gpu_is_unavailable(monkeypatch):
    monkeypatch.setattr(gpu, "current_os", lambda: "linux")
    monkeypatch.setattr(gpu, "_enumerate", lambda system: ([], []))
    monkeypatch.setattr(gpu, "_query_nvidia", lambda: None)
    sec = gpu.collect()
    assert sec.status is Status.UNAVAILABLE
    assert sec.status is not Status.ERROR


def test_collect_never_raises_on_real_host():
    sec = gpu.collect()
    assert sec.name == "gpu"
    assert sec.status is not Status.ERROR


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
