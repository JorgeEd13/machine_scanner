"""The one-page verdict: can this machine run a local AI model?

Written for someone who will not read a report. It answers in the first line,
fits one screen so a screenshot captures the whole thing, and names components
in the words on a spec sheet ("Graphics card", not "VRAM").

Two renderings, same content: ``to_requirements_text`` for a terminal or a
paste, ``to_requirements_html`` for the double-click case — self-contained,
inline CSS, no external asset (ADR-015).

**Displays, never computes.** Every verdict, threshold and pass/fail comes from
``advisor/`` and arrives here already decided.
"""

from __future__ import annotations

import html
from typing import List

from ..advisor.fit import ADVISOR_NAME, build_section, extract_profile
from ..advisor.requirements import Check, evaluate, failing, meets_tier
from ..core.models import Inventory
from .brand import FAVICON_LINK, MARK_B64

# Verdict → (headline, plain-language line). Three outcomes, no hedging: the
# reader has to know within one line which of the three they are.
_YES = "YES"
_LIMITED = "YES, WITH LIMITS"
_NOT_YET = "NOT YET"
_NO = "NO"

# Blockers the owner can clear without buying anything. Failing only on these is
# a different answer from failing on hardware: one is a ten-minute fix, the other
# is a purchase, and collapsing them into "NO" loses a machine that would qualify
# by the end of the conversation.
_SOFT_BLOCKERS = ("disk",)

# Printed on every report. The scope claim is only worth making if the reader
# can check it against what they are holding, so it ships with the output rather
# than living in a message they have to take on trust.
SCOPE_STATEMENT = (
    "This check read only: processor, memory, graphics card, free disk space, "
    "and whether Ollama and Docker are already installed. It did not collect "
    "your machine name, user name, network addresses or serial numbers."
)
READONLY_STATEMENT = (
    "Read-only: nothing was installed, changed, or sent anywhere. "
    "This page was written to your computer and nowhere else."
)


def _verdict(
    checks: List[Check], best_model: "dict | None", blockers: List[Check]
) -> "tuple[str, str]":
    if best_model is None or not meets_tier(checks, "minimum"):
        if blockers and all(c.key in _SOFT_BLOCKERS for c in blockers):
            return _NOT_YET, (
                "This machine has the hardware, but not enough free disk space yet."
            )
        return _NO, "This machine cannot run a local AI model well enough to be worth it."
    if meets_tier(checks, "recommended"):
        return _YES, "This machine can run a local AI model comfortably."
    return _LIMITED, "This machine can run a local AI model, but a smaller and slower one."


# ⚠️ MEASURED, not estimated (2026-07-29). Models at or below this quality rank
# — `qwen2.5:0.5b` and `qwen2.5:1.5b` — were run end to end against a real
# document set on a real 8 GB Windows machine, and the 1.5B produced a
# **confidently wrong answer about a policy it was citing**: asked about a
# sabbatical it stated that pay came "through overtime hours rather than in
# cash", where the document said the first four weeks are paid at full salary
# and there is no overtime clause in it. Eligibility, duration and return-to-role
# were correct in the same answer, which is what makes it dangerous. The same
# model also ignored an explicit instruction to answer in a named language.
#
# This tool's job is to say what a machine can run, and that is unchanged: these
# models DO run, and they stay in the range. But "smaller and slower" is the
# wrong caution to print over them — the problem is not speed, it is that the
# answers cannot be trusted, and a reader deciding whether this is worth doing
# needs that said plainly.
_UNRELIABLE_AT_OR_BELOW = 2


def _model_range(rows: List[dict]) -> List[dict]:
    """The models that fit, weakest first — the range this machine can run.

    Deliberately includes research-licensed models: "this machine can run X" is a
    true statement about the hardware, and hiding it would make the tool less
    honest. What must never come from this list is a RECOMMENDATION — see
    `_recommended`.
    """
    return sorted([r for r in rows if r["fits"]], key=lambda r: r["quality"])


def _recommended(rows: List[dict]) -> "dict | None":
    """The best model this machine can run **and lawfully use at work**.

    ⚠️ This exists because the report used to headline `fitting[-1]` — the best
    model that FITS — while `advisor.fit.recommend()` was carefully excluding
    non-commercial licences from its own `best`. The filter was computed and then
    thrown away one module later.

    Measured consequence: on a 4 GB machine `qwen2.5:3b` is both the highest-
    quality model that fits and the only Qwen2.5 size that is **not** Apache-2.0,
    so the page recommended a **Qwen Research License** model to a business —
    precisely the trap `catalog.py` says the licence fields exist to prevent, and
    the case that prompted them.

    The range keeps every fitting model; only the headline is filtered.
    """
    return max(
        (r for r in rows if r["fits"] and r.get("commercial", True)),
        key=lambda r: r["quality"],
        default=None,
    )


def _range_lines(ctx: dict) -> List[str]:
    """The model-range sentence, phrased for the verdict it sits under.

    A machine can be below the published bar and still have memory for a model —
    the usual cause is disk space, which is fixable in ten minutes. Printing
    "best available to you: llama3.1:8b" directly under a NO reads as a
    contradiction, so a failing machine gets the conditional phrasing instead:
    what it *would* run once the blockers are cleared.
    """
    fitting = ctx["fitting"]
    if not fitting:
        return ["No model in the catalogue fits this machine."]

    lo, hi = fitting[0], fitting[-1]
    if ctx["verdict"] in (_NO, _NOT_YET):
        blocked = ", ".join(c.label for c in ctx["blockers"])
        # "It has the memory for a model" is only true when memory is NOT the
        # blocker. Said under a memory blocker it directly contradicts the table
        # two lines above — seen on a real 8 GB Windows box, 2026-07-20.
        if all(c.key in _SOFT_BLOCKERS for c in ctx["blockers"]):
            return [
                f"Once the {blocked} requirement is met, this machine would run "
                f"{hi['name']}.",
                "It has the memory for a model — that is not what is blocking it.",
            ]
        return [
            f"Short of the minimum on: {blocked}.",
            "Meeting it would bring a small model within reach of this machine.",
        ]

    # The RANGE may name a research-licensed ceiling; the RECOMMENDATION may not.
    best = ctx.get("best")
    if best is None:
        return [
            f"This machine can run models from {lo['name']} to {hi['name']}.",
            "None of them is licensed for ordinary business use — every model "
            "that fits carries a research or community licence with conditions.",
        ]
    if lo["name"] == hi["name"]:
        return [
            f"This machine can run: {best['name']}  ({best['description']})"
        ] + _reliability_caution(best)
    lines = [f"This machine can run models from {lo['name']} to {hi['name']}."]
    lines.append(f"Best available to you: {best['name']}  ({best['description']})")
    if best["name"] != hi["name"]:
        # Say why the headline is not the ceiling, rather than letting the two
        # lines quietly disagree — the reader can see both names.
        lines.append(
            f"{hi['name']} would also fit, but its {hi.get('licence', 'licence')} "
            "is not one to rely on for business use."
        )
    return lines + _reliability_caution(best)


def _reliability_caution(best: "dict | None") -> List[str]:
    """The plain warning for the tiny band. See `_UNRELIABLE_AT_OR_BELOW`."""
    if best is None or best.get("quality", 99) > _UNRELIABLE_AT_OR_BELOW:
        return []
    return [
        "",
        "A model this small is not merely slower — in testing it answered "
        "questions about a document confidently and WRONGLY, while citing that "
        "document. Treat this size as a demonstration, not something to rely on "
        "for answers that matter.",
    ]


def _prepare(inventory: Inventory) -> dict:
    """Everything both renderers need, computed once."""
    section = inventory.section(ADVISOR_NAME) or build_section(inventory)
    profile = extract_profile(inventory)
    checks, disk_reasons = evaluate(inventory, profile)
    rows = section.data.get("models", [])
    fitting = _model_range(rows)
    # NOT `fitting[-1]` — see `_recommended`. The verdict and the headline are
    # both advice, and advice must not name a model the reader may not lawfully
    # run at work.
    best = _recommended(rows)
    blockers = failing(checks, "minimum")
    verdict, summary = _verdict(checks, best, blockers)
    return {
        "verdict": verdict,
        "summary": summary,
        "checks": checks,
        "fitting": fitting,
        "best": best,
        "disk_reasons": disk_reasons,
        "blockers": blockers,
        "notes": section.notes,
        "os": inventory.meta.get("os_detail", "unknown"),
    }


# --------------------------------------------------------------------------- #
# text
# --------------------------------------------------------------------------- #

_MARK = {True: "OK", False: "--"}


def _wrap(text: str, width: int) -> List[str]:
    """Wrap to ``width`` without importing textwrap for one call."""
    lines: List[str] = []
    line = ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        lines.append(line)
    return lines


def to_requirements_text(inventory: Inventory) -> str:
    ctx = _prepare(inventory)
    out: List[str] = [
        "",
        "  CAN THIS MACHINE RUN A LOCAL AI MODEL?",
        "  " + "=" * 62,
        "",
        f"  >> {ctx['verdict']}",
        f"     {ctx['summary']}",
        "",
        f"  {'Component':<16}{'This machine':<20}{'Minimum':<13}{'Recommended':<13}",
        "  " + "-" * 62,
    ]

    for check in ctx["checks"]:
        minimum = f"{_MARK[check.meets('minimum')]} {check.target_text('minimum')}"
        recommended = f"{_MARK[check.meets('recommended')]} {check.target_text('recommended')}"
        out.append(
            f"  {check.label[:15]:<16}{check.actual_text[:19]:<20}{minimum:<13}{recommended:<13}"
        )
        # The detail line carries what would not fit in the column — the card
        # name, or why the disk bar is not the published number. Wrapped, not
        # truncated: "+4 GB to install Do" is worse than no line at all.
        for line in _wrap(check.detail, 46):
            out.append(f"  {'':<16}{line}")

    out.append("")
    for line in _range_lines(ctx):
        out.append(f"  {line}")

    if ctx["blockers"]:
        out.append("")
        out.append("  Below the minimum:")
        for check in ctx["blockers"]:
            out.append(f"    - {check.label}: has {check.actual_text}, needs {check.target_text('minimum')}")

    if ctx["notes"]:
        out.append("")
        for note in ctx["notes"]:
            wrapped = _wrap(note, 60)
            out.append(f"  ! {wrapped[0]}")
            out.extend(f"    {line}" for line in wrapped[1:])

    out.append("")
    out.append("  " + "-" * 62)
    for statement in (SCOPE_STATEMENT, READONLY_STATEMENT):
        out.extend("  " + line for line in _wrap(statement, 62))

    out.append("")
    # Trailing spaces from the column padding survive a paste and look like
    # damage in a chat window.
    return "\n".join(line.rstrip() for line in out)


# --------------------------------------------------------------------------- #
# html
# --------------------------------------------------------------------------- #

_VERDICT_COLOR = {_YES: "#2e7d32", _LIMITED: "#ef6c00", _NOT_YET: "#ef6c00", _NO: "#c62828"}

_CSS = """
*{box-sizing:border-box}
body{margin:0;background:#eef0f4;color:#1a1c20;
     font-family:system-ui,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
     display:flex;justify-content:center;padding:24px 12px}
.sheet{background:#fff;max-width:760px;width:100%;border-radius:12px;overflow:hidden;
       box-shadow:0 2px 16px rgba(0,0,0,.12)}
.band{background:#0b0e14;color:#e8ecf2;padding:18px 26px;display:flex;
      align-items:center;gap:14px}
.band h1{font-size:1.02rem;margin:0;font-weight:600;letter-spacing:.2px}
.band .os{font-size:.78rem;color:#8b95a5;margin-top:2px}
.body{padding:26px}
.verdict{font-size:2rem;font-weight:700;margin:0 0 6px}
.summary{font-size:1.02rem;color:#3d434d;margin:0 0 22px}
table{width:100%;border-collapse:collapse;font-size:.94rem}
th{text-align:left;font-weight:600;color:#5b626d;font-size:.78rem;
   text-transform:uppercase;letter-spacing:.6px;padding:0 8px 8px;border-bottom:2px solid #e3e6ec}
td{padding:11px 8px;border-bottom:1px solid #eceef2;vertical-align:top}
td.num,th.num{text-align:right;white-space:nowrap}
.pass{color:#2e7d32;font-weight:700}
.fail{color:#c62828;font-weight:700}
.detail{display:block;color:#6b7280;font-size:.8rem;margin-top:3px}
.range{background:#f4f6fa;border-left:3px solid #0b0e14;padding:14px 16px;
       margin:22px 0 0;border-radius:0 6px 6px 0;font-size:.94rem}
.range strong{font-size:1.05rem}
.blockers{background:#fdf3f3;border-left:3px solid #c62828;padding:14px 16px;
          margin:16px 0 0;border-radius:0 6px 6px 0;font-size:.92rem}
.blockers ul{margin:8px 0 0;padding-left:18px}
.notes{margin:18px 0 0;color:#6b7280;font-size:.82rem}
.notes li{margin-bottom:4px}
.scope{margin:26px 0 0;padding-top:16px;border-top:1px solid #e3e6ec;
       color:#6b7280;font-size:.8rem;line-height:1.5}
.scope p{margin:0 0 6px}
@media print{body{background:#fff;padding:0}.sheet{box-shadow:none}}
"""


def _ascii(text: str) -> str:
    """Escape for HTML, then render every non-ASCII character as an entity.

    The page travels by email, chat upload and USB stick, through tools that do
    not all honour `<meta charset>`. A pure-ASCII file cannot be mis-decoded:
    an em dash becomes `&#8212;` rather than a byte sequence something downstream
    may read as cp1252 and turn into `â`. This repo has been bitten by exactly
    that class of bug before (ADR-016).
    """
    return html.escape(text).encode("ascii", "xmlcharrefreplace").decode("ascii")


def _row(check: Check) -> str:
    def cell(ok: bool, text: str) -> str:
        cls = "pass" if ok else "fail"
        mark = "&#10003;" if ok else "&#10007;"
        return f"<td class='num {cls}'>{mark} {_ascii(text)}</td>"

    detail = (
        f"<span class='detail'>{_ascii(check.detail)}</span>" if check.detail else ""
    )
    return (
        "<tr>"
        f"<td><strong>{_ascii(check.label)}</strong></td>"
        f"<td>{_ascii(check.actual_text)}{detail}</td>"
        f"{cell(check.meets('minimum'), check.target_text('minimum'))}"
        f"{cell(check.meets('recommended'), check.target_text('recommended'))}"
        "</tr>"
    )


def to_requirements_html(inventory: Inventory) -> str:
    ctx = _prepare(inventory)
    color = _VERDICT_COLOR[ctx["verdict"]]

    rows = "".join(_row(c) for c in ctx["checks"])

    range_html = "<br>".join(_ascii(line) for line in _range_lines(ctx))

    blockers = ""
    if ctx["blockers"]:
        items = "".join(
            f"<li><strong>{_ascii(c.label)}</strong> &mdash; has "
            f"{_ascii(c.actual_text)}, needs {_ascii(c.target_text('minimum'))}</li>"
            for c in ctx["blockers"]
        )
        blockers = f"<div class='blockers'>Below the minimum:<ul>{items}</ul></div>"

    notes = ""
    if ctx["notes"]:
        items = "".join(f"<li>{_ascii(n)}</li>" for n in ctx["notes"])
        notes = f"<ul class='notes'>{items}</ul>"

    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>Can this machine run a local AI model?</title>"
        f"{FAVICON_LINK}<style>{_CSS}</style></head><body><div class='sheet'>"
        "<div class='band'>"
        f"<img alt='' width='36' height='36' src='data:image/png;base64,{MARK_B64}'>"
        "<div><h1>Local AI model requirements</h1>"
        f"<div class='os'>{_ascii(ctx['os'])}</div></div></div>"
        "<div class='body'>"
        f"<p class='verdict' style='color:{color}'>{ctx['verdict']}</p>"
        f"<p class='summary'>{_ascii(ctx['summary'])}</p>"
        "<table><thead><tr><th>Component</th><th>This machine</th>"
        "<th class='num'>Minimum</th><th class='num'>Recommended</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        f"<div class='range'>{range_html}</div>"
        f"{blockers}{notes}"
        f"<div class='scope'><p>{_ascii(SCOPE_STATEMENT)}</p>"
        f"<p>{_ascii(READONLY_STATEMENT)}</p></div>"
        "</div></div></body></html>"
    )
