"""Requirements-check tests — offline, hardware-agnostic.

Same approach as the advisor tests: synthetic inventories, so the thresholds and
the pass/fail rules are asserted rather than the machine running the suite.
"""

import machine_scanner.collectors.llm_runtime as runtime
from machine_scanner.advisor.fit import extract_profile
from machine_scanner.advisor.requirements import (
    disk_requirement,
    evaluate,
    failing,
    meets_tier,
)
from machine_scanner.core.models import Inventory, Section, Status
from machine_scanner.qualifier import IDENTIFYING_META, SCOPE
from machine_scanner.report.requirements_report import (
    SCOPE_STATEMENT,
    to_requirements_html,
    to_requirements_text,
)

_NVIDIA_8GB = {
    "vendor": "NVIDIA",
    "name": "NVIDIA GeForce RTX 4060",
    "memory_total_mb": 8192.0,
    "driver_version": "550.54",
}


def _inv(memory=None, gpus=None, disk=None, cpu=None, ollama=True, docker=True) -> Inventory:
    sections = []
    if memory is not None:
        sections.append(Section("memory", "Memory", Status.OK, {"total_gb": memory}))
    if cpu is not None:
        sections.append(Section("cpu", "CPU", Status.OK, {"cores_logical": cpu}))
    if gpus is not None:
        sections.append(Section("gpu", "GPU", Status.OK, {"gpus": gpus}))
    if disk is not None:
        sections.append(Section("disk", "Disk", Status.OK, {"partitions": [{"free_gb": disk}]}))
    sections.append(
        Section(
            "llm_runtime", "LLM Runtime", Status.OK,
            {"ollama": {"installed": ollama}, "docker": {"installed": docker}},
        )
    )
    return Inventory(meta={"os_detail": "Test", "os": "windows"}, sections=sections)


def _checks(inv):
    return evaluate(inv, extract_profile(inv))[0]


# --------------------------------------------------------------------------- #
# memory passes by either route
# --------------------------------------------------------------------------- #

def test_plenty_of_ram_passes_with_no_graphics_card():
    checks = _checks(_inv(memory=32.0, disk=500.0, cpu=8))
    assert meets_tier(checks, "minimum")
    assert meets_tier(checks, "recommended")


def test_a_graphics_card_passes_with_modest_ram():
    # 8 GB of RAM alone misses the recommended bar; an 8 GB card clears it.
    checks = _checks(_inv(memory=8.0, gpus=[_NVIDIA_8GB], disk=500.0, cpu=8))
    assert meets_tier(checks, "recommended")


def test_neither_route_fails_the_machine():
    checks = _checks(_inv(memory=4.0, disk=500.0, cpu=8))
    assert not meets_tier(checks, "minimum")


def test_failing_reports_ram_once_not_both_memory_rows():
    # Telling someone they fail on two counts when adding RAM alone fixes it is
    # both discouraging and wrong.
    blockers = failing(_checks(_inv(memory=4.0, disk=500.0, cpu=8)), "minimum")
    keys = [c.key for c in blockers]
    assert keys.count("ram") == 1
    assert "vram" not in keys


# --------------------------------------------------------------------------- #
# the disk bar moves with what is already installed
# --------------------------------------------------------------------------- #

def test_disk_bar_is_the_published_number_when_prereqs_are_present():
    total, reasons = disk_requirement(_inv(memory=16.0), "minimum")
    assert total == 5.0
    assert reasons == []


def test_missing_prereqs_raise_the_disk_bar_and_say_why():
    total, reasons = disk_requirement(_inv(memory=16.0, ollama=False, docker=False), "minimum")
    assert total > 5.0
    assert len(reasons) == 2
    assert any("Ollama" in r for r in reasons)


def test_a_machine_can_fail_on_disk_only_because_of_missing_prereqs():
    # 6 GB free clears the published 5 GB bar, but not 5 + Ollama + Docker.
    ok = _checks(_inv(memory=32.0, disk=6.0, cpu=8))
    short = _checks(_inv(memory=32.0, disk=6.0, cpu=8, ollama=False, docker=False))
    assert meets_tier(ok, "minimum")
    assert not meets_tier(short, "minimum")


def test_absent_runtime_section_leaves_the_bar_alone():
    inv = Inventory(sections=[Section("memory", "Memory", Status.OK, {"total_gb": 16.0})])
    assert disk_requirement(inv, "minimum") == (5.0, [])


def test_install_cost_follows_the_scanned_os_not_the_rendering_one():
    # Docker Desktop (Windows/macOS) is a VM stack; the Linux engine is not.
    win = disk_requirement(_inv(memory=16.0, ollama=False, docker=False), "minimum")[0]
    linux_inv = _inv(memory=16.0, ollama=False, docker=False)
    linux_inv.meta["os"] = "linux"
    assert disk_requirement(linux_inv, "minimum")[0] < win


# --------------------------------------------------------------------------- #
# the report
# --------------------------------------------------------------------------- #

def test_strong_machine_reads_yes():
    text = to_requirements_text(_inv(memory=32.0, gpus=[_NVIDIA_8GB], disk=500.0, cpu=8))
    assert ">> YES" in text
    assert "WITH LIMITS" not in text


def test_borderline_machine_reads_yes_with_limits():
    text = to_requirements_text(_inv(memory=8.0, disk=500.0, cpu=4))
    assert "YES, WITH LIMITS" in text


def test_weak_machine_reads_no_and_names_what_is_missing():
    text = to_requirements_text(_inv(memory=4.0, disk=500.0, cpu=2))
    assert ">> NO" in text
    assert "Below the minimum:" in text
    assert "Memory (RAM)" in text


def test_report_states_its_own_scope():
    # The scope claim is only worth making if it ships with the output.
    for rendered in (
        to_requirements_text(_inv(memory=16.0, disk=500.0, cpu=8)),
        to_requirements_html(_inv(memory=16.0, disk=500.0, cpu=8)),
    ):
        assert "did not collect" in rendered
        assert "Read-only" in rendered


def test_text_report_has_no_trailing_whitespace():
    text = to_requirements_text(_inv(memory=32.0, gpus=[_NVIDIA_8GB], disk=500.0, cpu=8))
    assert all(line == line.rstrip() for line in text.splitlines())


def test_html_report_is_self_contained():
    html = to_requirements_html(_inv(memory=16.0, gpus=[_NVIDIA_8GB], disk=500.0, cpu=8))
    assert "src='http" not in html and 'src="http' not in html
    assert "href='http" not in html and 'href="http' not in html
    assert "data:image/png;base64," in html  # the brand mark, inlined


def test_html_escapes_a_hostile_gpu_name():
    card = dict(_NVIDIA_8GB, name="<script>alert(1)</script>")
    html = to_requirements_html(_inv(memory=16.0, gpus=[card], disk=500.0, cpu=8))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_report_survives_a_scan_with_nothing_in_it():
    to_requirements_text(Inventory())
    to_requirements_html(Inventory())


# --------------------------------------------------------------------------- #
# scope + privacy
# --------------------------------------------------------------------------- #

def test_qualifier_scope_excludes_the_identifying_collectors():
    for name in ("network", "usb", "monitors", "storage_devices", "baseboard", "bluetooth"):
        assert name not in SCOPE


def test_qualifier_strips_identifying_metadata(monkeypatch):
    import machine_scanner.qualifier as q

    inv = _inv(memory=16.0, disk=500.0, cpu=8)
    inv.meta.update({"hostname": "SECRET-PC", "user": "alice"})
    monkeypatch.setattr(q, "run_all", lambda only=None, autoload=True: inv)
    scanned = q._scan()
    for field in IDENTIFYING_META:
        assert field not in scanned.meta
    assert "SECRET-PC" not in to_requirements_html(scanned)


def test_scope_statement_matches_the_actual_scope():
    # If the scope list grows, the sentence promising what it reads must too.
    assert "graphics card" in SCOPE_STATEMENT.lower()
    assert "Docker" in SCOPE_STATEMENT
    assert len(SCOPE) == 5


# --------------------------------------------------------------------------- #
# the llm_runtime collector
# --------------------------------------------------------------------------- #

def test_runtime_found_on_path(monkeypatch):
    monkeypatch.setattr(runtime.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    section = runtime.collect()
    assert section.data["ollama"]["installed"] is True
    assert section.data["ollama"]["found_via"] == "PATH"


def test_runtime_found_at_a_known_install_location(monkeypatch):
    # Freshly installed on Windows: on disk, not yet on PATH.
    monkeypatch.setattr(runtime.shutil, "which", lambda cmd: None)
    monkeypatch.setattr(runtime, "_first_existing", lambda paths: "/opt/ollama/ollama")
    section = runtime.collect()
    assert section.data["ollama"]["found_via"] == "install location"


def test_runtime_absent_is_ok_not_a_failure(monkeypatch):
    monkeypatch.setattr(runtime.shutil, "which", lambda cmd: None)
    monkeypatch.setattr(runtime, "_first_existing", lambda paths: None)
    section = runtime.collect()
    assert section.status is Status.OK  # "not installed" is the answer, not a gap
    assert section.data["docker"]["installed"] is False
    assert any("not installed" in n for n in section.notes)


def test_unexpanded_windows_variable_is_skipped(monkeypatch):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert runtime._first_existing([r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"]) is None


def test_install_sizes_cover_every_os():
    for tool in ("ollama", "docker"):
        for system in ("windows", "linux", "macos", "other"):
            assert runtime.install_size_gb(tool, system) > 0


def test_a_disk_only_blocker_reads_not_yet_rather_than_no():
    # A ten-minute fix and a hardware purchase are different answers.
    text = to_requirements_text(
        _inv(memory=32.0, disk=6.0, cpu=8, ollama=False, docker=False)
    )
    assert ">> NOT YET" in text
    assert "free disk space yet" in text


def test_hardware_blocker_still_reads_no():
    text = to_requirements_text(_inv(memory=4.0, disk=500.0, cpu=2))
    assert ">> NO" in text


def test_failing_machine_never_claims_a_recommended_model():
    # "Best available to you: X" under a NO reads as a contradiction.
    text = to_requirements_text(_inv(memory=4.0, disk=500.0, cpu=2))
    assert "Best available to you" not in text


def test_an_unusable_card_is_named_rather_than_called_absent():
    igpu = {"vendor": "Intel", "name": "Intel(R) UHD Graphics 620", "memory_total_mb": 2048}
    text = to_requirements_text(_inv(memory=16.0, gpus=[igpu], disk=500.0, cpu=8))
    assert "UHD Graphics 620" in text
    assert "none detected" not in text


def test_qualifier_spec_bundles_exactly_the_scope():
    """The frozen build must contain the scoped collectors and no others.

    Drift here is silent and consequential in both directions: a missing module
    breaks the check on a client machine, and an extra one quietly widens what
    the binary is able to read while the report still claims otherwise.
    """
    import pathlib
    import re

    spec = pathlib.Path(__file__).parent.parent / "build" / "ai_model_requirements.spec"
    text = spec.read_text(encoding="utf-8")
    hidden = text.split("hiddenimports=[")[1].split("]")[0]
    bundled = set(re.findall(r"machine_scanner\.collectors\.(\w+)", hidden))
    assert bundled == set(SCOPE)

    excluded = text.split("excludes=[")[1].split("]")[0]
    left_out = set(re.findall(r"machine_scanner\.collectors\.(\w+)", excluded))
    assert not (bundled & left_out)
    # Every collector MODULE is accounted for: bundled or explicitly excluded.
    # (Module name != collector name — `input_devices` registers as `input`.)
    modules = {
        path.stem
        for path in (pathlib.Path(__file__).parent.parent
                     / "src" / "machine_scanner" / "collectors").glob("*.py")
        if not path.stem.startswith("_")
    }
    assert modules == bundled | (left_out - {"_all"})


def test_importing_a_collector_does_not_drag_in_the_others():
    """The property the spec's excludes depend on (ADR-021).

    Needs a fresh interpreter: this process has already imported the manifest,
    so `sys.modules` here proves nothing. The subprocess **inherits** the real
    environment with only PYTHONPATH added — replacing it outright breaks Python
    startup on Windows, which needs SYSTEMROOT and friends to boot at all.
    """
    import os
    import pathlib
    import subprocess
    import sys

    src = pathlib.Path(__file__).parent.parent / "src"
    code = (
        "import machine_scanner.collectors.cpu, sys;"
        "loaded=[m for m in sys.modules if m.startswith('machine_scanner.collectors.')];"
        "print(sorted(loaded))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True,
        env=dict(os.environ, PYTHONPATH=str(src)),
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "collectors.cpu" in out  # the import under test actually happened
    for excluded in ("network", "usb", "storage_devices", "bluetooth"):
        assert excluded not in out
