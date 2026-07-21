"""Advisor tests — offline and hardware-agnostic.

Every case builds a synthetic Inventory, so these assert the *heuristic*, never
the machine running them. That is the point of deriving instead of probing: the
whole decision surface is reachable from a dict.
"""

import pytest

from machine_scanner.advisor import build_section, extract_profile, recommend, to_summary
from machine_scanner.advisor.fit import ADVISOR_NAME, append_to
from machine_scanner.core.models import Inventory, Section, Status


def _inventory(memory=None, gpus=None, disk=None, cpu=None) -> Inventory:
    sections = []
    if memory is not None:
        sections.append(Section("memory", "Memory", Status.OK, {"total_gb": memory}))
    if cpu is not None:
        sections.append(Section("cpu", "CPU", Status.OK, {"cores_logical": cpu}))
    if gpus is not None:
        sections.append(Section("gpu", "GPU", Status.OK, {"gpus": gpus}))
    if disk is not None:
        sections.append(
            Section("disk", "Disk", Status.OK, {"partitions": [{"free_gb": disk}]})
        )
    return Inventory(meta={"hostname": "box", "os_detail": "Test", "version": "0.1.0"}, sections=sections)


_NVIDIA_8GB = {
    "vendor": "NVIDIA",
    "name": "NVIDIA GeForce RTX 4060",
    "memory_total_mb": 8192.0,
    "driver_version": "550.54",
}
_INTEL_IGPU = {"vendor": "Intel", "name": "Intel(R) UHD Graphics 620", "memory_total_mb": 2048}


# --------------------------------------------------------------------------- #
# usable memory: the core heuristic
# --------------------------------------------------------------------------- #

def test_cpu_path_reserves_headroom_from_total_ram():
    profile = extract_profile(_inventory(memory=16.0))
    assert profile.accelerated is False
    assert profile.usable_memory_gb == 12.8  # 80% of 16
    assert "system RAM" in profile.memory_basis


def test_gpu_path_sizes_on_vram_not_ram():
    # A box with a lot of RAM and a small GPU is still sized on the GPU: that is
    # where the model actually runs.
    profile = extract_profile(_inventory(memory=64.0, gpus=[_NVIDIA_8GB]))
    assert profile.accelerated is True
    assert profile.usable_memory_gb == 8.0
    assert profile.memory_basis == "GPU VRAM"


def test_integrated_gpu_is_not_counted_as_vram():
    # The double-counting trap: an iGPU's "memory" is the same RAM already
    # counted, so it must not become the sizing basis.
    profile = extract_profile(_inventory(memory=8.0, gpus=[_INTEL_IGPU]))
    assert profile.accelerated is False
    assert profile.usable_memory_gb == 6.4


def test_discrete_gpu_wins_over_integrated_on_a_hybrid_laptop():
    profile = extract_profile(_inventory(memory=16.0, gpus=[_INTEL_IGPU, _NVIDIA_8GB]))
    assert profile.accelerated is True
    assert profile.usable_memory_gb == 8.0


def test_tiny_vram_falls_back_to_the_cpu_path():
    weak = {"vendor": "NVIDIA", "name": "GeForce GT 710", "memory_total_mb": 512}
    profile = extract_profile(_inventory(memory=8.0, gpus=[weak]))
    assert profile.accelerated is False


# --------------------------------------------------------------------------- #
# recommendation
# --------------------------------------------------------------------------- #

def test_stronger_hardware_never_recommends_a_weaker_model():
    weak, _ = recommend(extract_profile(_inventory(memory=4.0, disk=500.0)))
    strong, _ = recommend(extract_profile(_inventory(memory=64.0, disk=500.0)))
    assert strong["quality"] >= weak["quality"]


def test_nothing_fits_a_machine_below_the_floor():
    best, rows = recommend(extract_profile(_inventory(memory=0.5, disk=500.0)))
    assert best is None
    assert all(row["fits"] is False for row in rows)


def test_disk_can_veto_a_model_that_fits_in_memory():
    profile = extract_profile(_inventory(memory=64.0, disk=2.5))
    best, rows = recommend(profile)
    # 64 GB of RAM clears every model on memory; 2.5 GB of disk does not.
    assert best is not None
    assert best["disk_required_gb"] <= 2.5
    assert any(row["fits_memory"] and not row["fits_disk"] for row in rows)


def test_unknown_free_disk_does_not_veto_anything():
    # Absent information is not evidence of a full disk.
    _, rows = recommend(extract_profile(_inventory(memory=64.0)))
    assert all(row["fits_disk"] for row in rows)


# --------------------------------------------------------------------------- #
# the section
# --------------------------------------------------------------------------- #

def test_section_is_unavailable_without_memory_or_gpu():
    section = build_section(_inventory(cpu=8))
    assert section.status is Status.UNAVAILABLE
    assert section.notes


def test_unusable_verdict_is_ok_status_not_an_error():
    # "This machine cannot run one" is a successful answer, not a failed scan.
    section = build_section(_inventory(memory=0.5, disk=500.0))
    assert section.status is Status.OK
    assert section.data["verdict"] == "unusable"
    assert section.data["recommended_model"] is None


def test_strong_box_reads_comfortable():
    section = build_section(_inventory(memory=32.0, gpus=[_NVIDIA_8GB], disk=500.0, cpu=16))
    assert section.data["verdict"] == "comfortable"
    assert section.data["gpu_accelerated"] is True


def test_saturated_windows_vram_reading_is_flagged():
    # No driver_version => the row came from the OS adapter table, whose 32-bit
    # field saturates at 4 GB. The number is used, the caveat is stated.
    card = {"vendor": "AMD", "name": "Radeon RX 7900 XTX", "memory_total_mb": 4096}
    section = build_section(_inventory(memory=32.0, gpus=[card], disk=500.0))
    assert any("saturates" in note for note in section.notes)


def test_non_nvidia_gpu_carries_a_driver_stack_caveat():
    card = {
        "vendor": "AMD",
        "name": "Radeon RX 6800",
        "memory_total_mb": 16384,
        "driver_version": "1.0",
    }
    section = build_section(_inventory(memory=32.0, gpus=[card], disk=500.0))
    assert any("driver stack" in note for note in section.notes)


def test_few_cores_warns_only_on_the_cpu_path():
    on_cpu = build_section(_inventory(memory=16.0, disk=500.0, cpu=2))
    on_gpu = build_section(_inventory(memory=16.0, gpus=[_NVIDIA_8GB], disk=500.0, cpu=2))
    assert any("logical cores" in note for note in on_cpu.notes)
    assert not any("logical cores" in note for note in on_gpu.notes)


def test_malformed_gpu_section_does_not_raise():
    inv = Inventory(sections=[Section("gpu", "GPU", Status.OK, {"gpus": "not-a-list"})])
    assert build_section(inv).status is Status.UNAVAILABLE


# --------------------------------------------------------------------------- #
# wiring + the pasteable summary
# --------------------------------------------------------------------------- #

def test_append_to_respects_an_only_filter():
    assert append_to(_inventory(memory=16.0), only=["cpu"]).section(ADVISOR_NAME) is None
    assert append_to(_inventory(memory=16.0), only=None).section(ADVISOR_NAME) is not None
    assert append_to(_inventory(memory=16.0), only=[ADVISOR_NAME]).section(ADVISOR_NAME) is not None


def test_summary_leads_with_the_verdict_and_stays_short():
    inventory = append_to(_inventory(memory=32.0, gpus=[_NVIDIA_8GB], disk=500.0, cpu=16))
    text = to_summary(inventory)
    assert "COMFORTABLE" in text
    assert inventory.section(ADVISOR_NAME).data["recommended_model"] in text
    assert len(text.splitlines()) < 25  # it has to survive being pasted into a chat box


def test_summary_says_unknown_rather_than_guessing():
    text = to_summary(_inventory(cpu=4))
    assert "UNKNOWN" in text


@pytest.mark.parametrize("ram", [1.0, 4.0, 8.0, 16.0, 32.0, 128.0])
def test_every_ram_size_produces_a_coherent_section(ram):
    section = build_section(_inventory(memory=ram, disk=500.0, cpu=8))
    assert section.status in (Status.OK, Status.PARTIAL)
    assert section.data["verdict"] in ("unusable", "minimal", "workable", "comfortable")
    assert len(section.data["models"]) == 9


# ------------------------------------------------------------- licensing ---
#
# A model being free to download does not mean it is free to use at work: open
# WEIGHTS are not open SOURCE. `qwen2.5:3b` is the case that matters here —
# every other Qwen2.5 size in the catalog is Apache-2.0 and the 3B is under a
# research licence, and it is the highest-quality model that fits a modest 4 GB
# machine, so it was exactly the one this tool would have headlined.


def test_a_research_licensed_model_is_never_the_recommendation():
    # 8 GB: comfortably enough for the 3B class, which is where the trap sits.
    best, rows = recommend(extract_profile(_inventory(memory=8.0, disk=500.0)))

    assert best is not None
    assert best["commercial"] is True
    assert best["name"] != "qwen2.5:3b"

    trap = next(row for row in rows if row["name"] == "qwen2.5:3b")
    assert trap["fits"] is True, "the point is that it FITS and is still not chosen"


def test_a_restricted_model_is_still_LISTED_with_its_licence():
    """Hiding it would make the tool less honest, not safer. It is a true
    statement about what the machine can run; the licence lets the reader
    decide."""
    _, rows = recommend(extract_profile(_inventory(memory=8.0, disk=500.0)))

    trap = next(row for row in rows if row["name"] == "qwen2.5:3b")
    assert trap["commercial"] is False
    assert trap["licence"] == "Qwen Research License"


def test_every_model_carries_a_licence_name():
    _, rows = recommend(extract_profile(_inventory(memory=64.0, disk=500.0)))

    assert all(row["licence"] for row in rows)


def test_excluding_it_does_not_leave_a_4gb_machine_without_a_recommendation():
    best, _ = recommend(extract_profile(_inventory(memory=8.0, disk=500.0)))

    assert best is not None
    assert best["quality"] >= 4
