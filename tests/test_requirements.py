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


# --------------------------------------------------------------------------- #
# found on a real Windows 8 GB machine, 2026-07-20
# --------------------------------------------------------------------------- #

def test_an_8gb_machine_clears_the_8gb_bar():
    """Reported RAM is always under the sticker size, so 7.9 GB IS an 8 GB box.

    The original bars rejected exactly the machines they were written to admit.
    """
    checks = _checks(_inv(memory=7.9, disk=46.0, cpu=4))
    ram = next(c for c in checks if c.key == "ram")
    assert ram.meets("minimum")
    assert "8 GB" in ram.actual_text
    assert "7.9" in ram.detail  # the reported figure is still disclosed


def test_a_16gb_laptop_with_an_igpu_clears_the_16gb_bar():
    # An iGPU can reserve ~9% of system RAM; 14.57 GB is a 16 GB machine.
    checks = _checks(_inv(memory=14.57, disk=500.0, cpu=16))
    assert next(c for c in checks if c.key == "ram").meets("recommended")


def test_an_unusual_size_is_not_rounded_up_to_memory_it_lacks():
    checks = _checks(_inv(memory=6.32, disk=500.0, cpu=4))
    ram = next(c for c in checks if c.key == "ram")
    assert ram.actual == 6.32
    assert not ram.meets("minimum")


def test_the_windows_8gb_box_reads_yes_with_limits_not_no():
    igpu = {"vendor": "Intel", "name": "Intel(R) HD Graphics", "memory_total_mb": 1024}
    text = to_requirements_text(_inv(memory=7.9, gpus=[igpu], disk=46.0, cpu=4))
    assert "YES, WITH LIMITS" in text
    assert ">> NO" not in text


def test_a_memory_blocker_never_claims_the_machine_has_the_memory():
    """The sentence contradicted the table two lines above it."""
    text = to_requirements_text(_inv(memory=3.0, disk=500.0, cpu=4))
    assert "has the memory for a model" not in text
    assert "Short of the minimum on" in text


def test_a_disk_only_blocker_still_says_memory_is_not_the_problem():
    text = to_requirements_text(
        _inv(memory=32.0, disk=6.0, cpu=8, ollama=False, docker=False)
    )
    assert "has the memory for a model" in text


def test_html_output_is_pure_ascii():
    """A page that travels by email/chat must not depend on charset handling."""
    igpu = {"vendor": "Intel", "name": "Intel(R) HD Gráficos —", "memory_total_mb": 1024}
    html = to_requirements_html(_inv(memory=7.9, gpus=[igpu], disk=46.0, cpu=4))
    html.encode("ascii")  # raises if any non-ASCII byte survives
    assert "&#" in html  # ...because the non-ASCII became entities, not because it vanished


# ------------------------------- the licence filter, at REPORT level (2026-07-29)
#
# `advisor.fit.recommend()` has always excluded non-commercial licences from its
# `best`, and `test_advisor_fit.py` asserts it. The REPORT recomputed its own
# `best = fitting[-1]` and threw that filter away, so the page headlined the
# highest-quality model that FITS regardless of licence.
#
# ⚠️ The existing licence test sits at 8 GB, where the ceiling is commercial
# anyway — so it could never have caught this. The trap only bites between
# 4 and 6 GB, where `qwen2.5:3b` (Qwen Research License) IS the ceiling. A test
# in the right file at the wrong size is a test that proves nothing.


def _four_gb_gpu():
    """16 GB RAM, 4 GB VRAM — passes the minimum tier, and its accelerated
    ceiling is `qwen2.5:3b`, the one research-licensed size in the catalog.

    ⚠️ Getting this machine right IS the test. A 5 GB CPU box also has that
    ceiling, but it fails the minimum tier so no model is ever named — the
    report never reaches the line under test. A fixture that cannot reach the
    code proves nothing, which is how the first draft of this test passed
    against the defect.
    """
    gpu = [{
        "vendor": "NVIDIA", "name": "NVIDIA GeForce RTX 3050",
        "memory_total_mb": 4096.0, "driver_version": "550.54",
    }]
    return _inv(memory=16.0, disk=500.0, cpu=8, gpus=gpu)


def test_the_report_never_HEADLINES_a_research_licensed_model():
    text = to_requirements_text(_four_gb_gpu())

    headline = [ln for ln in text.splitlines() if "Best available to you" in ln]
    assert headline, "a machine that fits a model must get a recommendation line"
    assert "qwen2.5:3b" not in headline[0], (
        "the page recommended a Qwen Research License model for business use"
    )
    assert "llama3.2:3b" in headline[0]


def test_the_report_still_LISTS_the_research_licensed_ceiling():
    """Honesty cuts both ways: it fits, and saying so is true.

    Only the RECOMMENDATION is filtered — hiding the model would make the tool
    less honest, which is the reasoning `recommend()` already records.
    """
    text = to_requirements_text(_four_gb_gpu())

    assert "qwen2.5:3b" in text, "the model that fits must still be named"


def test_the_report_SAYS_WHY_the_headline_is_not_the_ceiling():
    """Otherwise two lines on one page quietly disagree and the reader is left
    to wonder which is wrong — the failure mode `dgp-05` showed between the HTML
    and the pasteable summary."""
    text = to_requirements_text(_four_gb_gpu())

    assert "Qwen Research License" in text


def test_the_html_report_agrees_with_the_text_report():
    """They disagreed on `dgp-05`: the HTML headlined llama3.1:8b while the
    pasteable summary said qwen2.5:7b. Two renderers of one decision must not
    diverge."""
    inv = _four_gb_gpu()
    html = to_requirements_html(inv)
    headline = [
        ln for ln in to_requirements_text(inv).splitlines()
        if "Best available to you" in ln
    ][0]

    assert "llama3.2:3b" in headline
    assert "llama3.2:3b" in html


# --------------------------- the tiny-model reliability caution (2026-07-29) ---
#
# Measured, not estimated: `qwen2.5:1.5b` was run end to end against a real
# document set and stated that sabbatical pay came "through overtime hours
# rather than in cash", citing a document that says the first four weeks are
# paid at full salary and contains no overtime clause. The verdict line above it
# says "smaller and slower", which is the wrong caution — the problem is not
# speed.


def _tiny_band():
    """16 GB RAM, 2 GB VRAM — passes the minimum tier, and its best model is
    `qwen2.5:1.5b`.

    ⚠️ The GPU is what makes this reachable. On the CPU path a machine whose
    best model is 1.5B has under 5 GB of RAM, fails the minimum tier, and never
    reaches a recommendation line at all — so a CPU fixture would assert nothing.
    """
    gpu = [{
        "vendor": "NVIDIA", "name": "NVIDIA GeForce GTX 1050",
        "memory_total_mb": 2048.0, "driver_version": "550.54",
    }]
    return _inv(memory=16.0, disk=500.0, cpu=8, gpus=gpu)


def test_a_tiny_model_recommendation_carries_the_reliability_caution():
    text = to_requirements_text(_tiny_band())

    assert "Best available to you: qwen2.5:1.5b" in text
    assert "not merely slower" in text
    assert "confidently and WRONGLY" in text


def test_a_capable_machine_gets_NO_reliability_caution():
    """The caution must be band-specific. Printed over a 7B recommendation it
    would be false, and a warning that appears everywhere is read nowhere."""
    text = to_requirements_text(_inv(memory=32.0, disk=500.0, cpu=8))

    assert "Best available to you" in text
    assert "not merely slower" not in text
