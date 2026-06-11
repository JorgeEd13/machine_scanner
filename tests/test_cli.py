"""CLI-level tests — exit codes and the basic output paths.

Offline and hardware-agnostic: we drive ``cli.main`` directly and, where the
result must be deterministic, stub the scan with a controlled Inventory.
"""

import machine_scanner.cli as cli
from machine_scanner.core.models import Inventory, Section, Status


def _stub_scan(monkeypatch, *sections: Section) -> None:
    inv = Inventory(meta={"version": "0.1.0"}, sections=list(sections))
    monkeypatch.setattr(cli, "run_all", lambda only=None: inv)


def test_clean_scan_exits_zero(monkeypatch, capsys):
    _stub_scan(monkeypatch, Section("cpu", "CPU", Status.OK, {"cores_logical": 4}))
    assert cli.main([]) == cli.EXIT_OK


def test_partial_scan_still_exits_zero(monkeypatch, capsys):
    # An expected gap is not a failure.
    _stub_scan(monkeypatch, Section("gpu", "GPU", Status.UNAVAILABLE))
    assert cli.main([]) == cli.EXIT_OK


def test_errored_collector_exits_nonzero(monkeypatch, capsys):
    _stub_scan(
        monkeypatch,
        Section("cpu", "CPU", Status.OK, {"cores_logical": 4}),
        Section("boom", "BOOM", Status.ERROR, notes=["RuntimeError: kaboom"]),
    )
    assert cli.main([]) == cli.EXIT_COLLECTOR_ERROR


def test_list_exits_zero(monkeypatch, capsys):
    assert cli.main(["--list"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "cpu" in out


def test_json_output_is_emitted(monkeypatch, capsys):
    _stub_scan(monkeypatch, Section("cpu", "CPU", Status.OK, {"cores_logical": 4}))
    cli.main(["--json"])
    out = capsys.readouterr().out
    assert '"cores_logical": 4' in out
