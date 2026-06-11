"""Regression tests for subprocess text decoding (mojibake fix).

PowerShell 5.1 writes stdout in the console OEM code page (e.g. cp850 on a
pt-BR box). Decoding that with the locale code page (cp1252) silently
mis-decodes accented characters into the *captured data* — `ç`→`‡`, `ã`→`Æ` —
so the JSON itself was wrong, not just the console. The fix: force PowerShell to
emit UTF-8 and decode subprocess output as UTF-8.

These tests are offline (subprocess / run_command are stubbed) and build the
non-ASCII bytes via ``chr()`` so the test source stays ASCII.
"""

from machine_scanner.collectors import _smbios
from machine_scanner.core import platform as plat


def test_run_command_decodes_as_utf8(monkeypatch):
    captured = {}

    class _Fake:
        stdout = "ok"

    def fake_run(args, **kwargs):
        captured.update(kwargs)
        return _Fake()

    monkeypatch.setattr(plat.subprocess, "run", fake_run)

    assert plat.run_command(["anything"]) == "ok"
    assert captured.get("encoding") == "utf-8"
    assert captured.get("errors") == "replace"


def test_run_cim_forces_utf8_prefix_and_strips_bom(monkeypatch):
    bom = chr(0xFEFF)
    cedilla = chr(0xE7)  # ç
    seen = {}

    def fake_run_command(args, timeout=20.0):
        seen["args"] = args
        # Simulate PowerShell emitting JSON with a leading BOM + accented value.
        return bom + '{"name": "Aperfei' + cedilla + 'oado"}'

    monkeypatch.setattr(_smbios, "run_command", fake_run_command)

    rows = _smbios.run_cim("Get-CimInstance Win32_Keyboard | ConvertTo-Json")

    # The forced-UTF8 prefix is prepended to the script that PowerShell runs.
    command = seen["args"][-1]
    assert command.startswith(_smbios.POWERSHELL_UTF8)
    assert "Win32_Keyboard" in command
    # BOM stripped and the accented character survives intact.
    assert rows == [{"name": "Aperfei" + cedilla + "oado"}]


def test_strip_bom_removes_only_a_leading_bom():
    bom = chr(0xFEFF)
    assert _smbios._strip_bom(bom + "x") == "x"
    assert _smbios._strip_bom("x") == "x"
    # A BOM mid-string is left alone (only a leading one is a parse hazard).
    assert _smbios._strip_bom("a" + bom + "b") == "a" + bom + "b"
