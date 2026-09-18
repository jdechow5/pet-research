"""Outputs: a self-contained HTML working dashboard, plus CSV and JSON.

The HTML is one file with no external assets, so it keeps working offline
and a year from now. It leads with the funnel counts, because the first
question about a protocol this strict is always "how many survived", and
every claim carries the quote and link it came from.
"""

from __future__ import annotations

import csv
import html
import json
from pathlib import Path

from .models import Candidate, SizeVerdict, to_jsonable
from .protocol import ProtocolRun

SIZE_LABELS = {
    SizeVerdict.STANDARD_CONFIRMED: ("Standard confirmed", "good"),
    SizeVerdict.STANDARD_LIKELY: ("Standard likely", "ok"),
    SizeVerdict.UNKNOWN: ("Size not stated", "warn"),
    SizeVerdict.STANDARD_UNLIKELY: ("Standard unlikely", "bad"),
    SizeVerdict.STANDARD_EXCLUDED: ("Not a standard program", "bad"),
}

CSS = """
:root {
  --bg: #fbfaf8; --panel: #ffffff; --ink: #1b1a17; --muted: #6a675f;
  --line: #e4e0d8; --accent: #5a6e4f; --accent-soft: #eef1ea;
  --good: #3f6b46; --ok: #6a6a2f; --warn: #8a5d1c; --bad: #8c3b33;
  --shadow: 0 1px 2px rgba(0,0,0,.05), 0 4px 16px rgba(0,0,0,.04);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #15161a; --panel: #1d1f24; --ink: #ecebe7; --muted: #9b988f;
    --line: #2e3138; --accent: #9dbb8c; --accent-soft: #23282210;
    --good: #8fbf98; --ok: #c3c07a; --warn: #d9a866; --bad: #e08b80;
    --shadow: none;
  }
}
:root[data-theme="dark"] {
  --bg: #15161a; --panel: #1d1f24; --ink: #ecebe7; --muted: #9b988f;
  --line: #2e3138; --accent: #9dbb8c; --accent-soft: #232822;
  --good: #8fbf98; --ok: #c3c07a; --warn: #d9a866; --bad: #e08b80;
  --shadow: none;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 16px/1.55 ui-sans-serif, -apple-system, "Segoe UI", Roboto, sans-serif;
  -webkit-text-size-adjust: 100%;
}
.wrap { max-width: 1040px; margin: 0 auto; padding: 32px 16px 96px; }
h1 { font-size: 1.6rem; margin: 0 0 6px; letter-spacing: -.01em; }
h2 { font-size: 1.15rem; margin: 40px 0 12px; }
h3 { font-size: 1.02rem; margin: 0; }
p { margin: 0 0 12px; }
a { color: var(--accent); text-decoration-thickness: 1px; text-underline-offset: 2px; }
.sub { color: var(--muted); font-size: .9rem; margin-bottom: 28px; }
.panel {
  background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
  padding: 18px; margin-bottom: 14px; box-shadow: var(--shadow);
}
.funnel { display: grid; gap: 8px; }
.step { display: grid; grid-template-columns: 1fr auto; gap: 12px; align-items: start;
  padding: 12px 14px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel); }
.step .name { font-weight: 600; }
.step .desc { color: var(--muted); font-size: .86rem; margin-top: 3px; }
.count { font-variant-numeric: tabular-nums; font-size: 1.5rem; font-weight: 650; color: var(--accent); }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
  padding: 18px; margin-bottom: 14px; box-shadow: var(--shadow); }
.card-head { display: flex; flex-wrap: wrap; gap: 10px; justify-content: space-between; align-items: baseline; }
.score { font-variant-numeric: tabular-nums; font-weight: 700; color: var(--accent); white-space: nowrap; }
.meta { color: var(--muted); font-size: .88rem; margin: 4px 0 12px; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 0 12px; }
.chip { font-size: .78rem; padding: 3px 9px; border-radius: 999px; border: 1px solid var(--line);
  background: var(--accent-soft); color: var(--ink); }
.chip.good { color: var(--good); border-color: currentColor; }
.chip.ok { color: var(--ok); border-color: currentColor; }
.chip.warn { color: var(--warn); border-color: currentColor; }
.chip.bad { color: var(--bad); border-color: currentColor; }
.sig { display: grid; grid-template-columns: 18px 1fr; gap: 8px; padding: 5px 0;
  border-top: 1px dashed var(--line); font-size: .92rem; }
.sig:first-child { border-top: 0; }
.mark { font-weight: 700; }
.mark.y { color: var(--good); } .mark.n { color: var(--muted); } .mark.p { color: var(--warn); }
blockquote { margin: 5px 0 0; padding-left: 10px; border-left: 2px solid var(--line);
  color: var(--muted); font-size: .84rem; }
ul { margin: 6px 0 0; padding-left: 20px; }
li { margin-bottom: 4px; }
table { width: 100%; border-collapse: collapse; font-size: .9rem; }
th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { color: var(--muted); font-weight: 600; font-size: .8rem; text-transform: uppercase; letter-spacing: .04em; }
.scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
details { border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px;
  background: var(--panel); margin-bottom: 12px; }
summary { cursor: pointer; font-weight: 600; }
code { font-size: .85em; background: var(--accent-soft); padding: 1px 5px; border-radius: 4px; }
.caveat { border-left: 3px solid var(--warn); padding-left: 14px; }
.empty { color: var(--muted); font-style: italic; }
.sample { border: 1px solid var(--bad); border-left-width: 4px; border-radius: 8px;
  padding: 14px 16px; margin-bottom: 22px; background: var(--panel); }
.sample strong { color: var(--bad); }
.links a { display: inline-block; margin: 0 10px 6px 0; font-size: .88rem; }
"""


def _esc(value) -> str:
    return html.escape(str(value if value is not None else ""))


def _mark(signal) -> tuple[str, str]:
    if signal.points >= 0.99:
        return "Y", "y"
    if signal.points > 0:
        return "~", "p"
    return "-", "n"


def _candidate_card(candidate: Candidate, *, rank: int | None = None) -> str:
    size_label, size_tone = SIZE_LABELS.get(
        candidate.size.verdict, ("Size unknown", "warn")
    )
    title = _esc(candidate.kennel)
    if rank:
        title = f"{rank}. {title}"

    chips = [f'<span class="chip {size_tone}">{_esc(size_label)}</span>']
    for award in candidate.alaa_awards:
        tone = "good" if award.lower().startswith("platinum") else ""
        chips.append(f'<span class="chip {tone}">ALAA {_esc(award)}</span>')
    for award in candidate.wala_awards:
        tone = "good" if "diamond" in award.lower() else "warn"
        chips.append(f'<span class="chip {tone}">WALA {_esc(award)}</span>')
    if candidate.match.status == "review":
        chips.append('<span class="chip warn">cross-registry match unconfirmed</span>')

    travel = candidate.signal("travel_band")
    location = candidate.city or candidate.region or "location not listed"
    meta = f"{_esc(location)}"
    if candidate.region and candidate.city:
        meta = f"{_esc(candidate.city)}, {_esc(candidate.region)}"
    if travel and travel.value:
        meta += f" &middot; {_esc(travel.value)}"
    if candidate.website:
        meta += f' &middot; <a href="{_esc(candidate.website)}" rel="noopener">site</a>'

    rows = []
    for signal in candidate.signals:
        if signal.key == "travel_band":
            continue
        mark, tone = _mark(signal)
        body = f"<strong>{_esc(signal.label)}</strong> &mdash; {_esc(signal.value)}"
        for evidence in signal.evidence[:2]:
            body += (
                f'<blockquote>&ldquo;{_esc(evidence.short())}&rdquo;'
                + (
                    f' <a href="{_esc(evidence.source_url)}" rel="noopener">source</a>'
                    if evidence.source_url
                    else ""
                )
                + "</blockquote>"
            )
        rows.append(
            f'<div class="sig"><span class="mark {tone}">{mark}</span>'
            f"<div>{body}</div></div>"
        )

    followups = ""
    if candidate.followups:
        items = "".join(f"<li>{_esc(f)}</li>" for f in candidate.followups)
        followups = f"<p style='margin-top:12px'><strong>Before you contact them</strong></p><ul>{items}</ul>"

    exclusions = ""
    if candidate.exclusion_reasons:
        items = "".join(f"<li>{_esc(r)}</li>" for r in candidate.exclusion_reasons)
        exclusions = f"<p style='margin-top:12px'><strong>Why this one did not clear the protocol</strong></p><ul>{items}</ul>"

    links = ""
    if candidate.verification_links:
        anchors = "".join(
            f'<a href="{_esc(url)}" rel="noopener">{_esc(label)}</a>'
            for label, url in candidate.verification_links.items()
        )
        links = f'<p style="margin-top:12px"><strong>Verify independently</strong></p><div class="links">{anchors}</div>'

    match_note = ""
    if candidate.match.basis:
        basis = "; ".join(_esc(b) for b in candidate.match.basis)
        match_note = f'<p class="meta" style="margin-top:12px">Registry join: {basis}.</p>'

    return f"""<div class="card">
  <div class="card-head"><h3>{title}</h3><span class="score">{candidate.score:g}</span></div>
  <div class="meta">{meta}</div>
  <div class="chips">{''.join(chips)}</div>
  {''.join(rows)}
  {followups}{exclusions}{links}{match_note}
</div>"""


def _funnel(run: ProtocolRun) -> str:
    steps = []
    for entry in run.funnel:
        detail = (
            f'<div class="desc">{_esc(entry["detail"])}</div>' if entry.get("detail") else ""
        )
        steps.append(
            f'<div class="step"><div><div class="name">{_esc(entry["stage"])}</div>'
            f'<div class="desc">{_esc(entry["description"])}</div>{detail}</div>'
            f'<div class="count">{entry["remaining"]}</div></div>'
        )
    return f'<div class="funnel">{"".join(steps)}</div>'


def _near_miss_table(candidates: list[Candidate]) -> str:
    if not candidates:
        return '<p class="empty">Nothing here.</p>'
    rows = []
    for candidate in candidates:
        reasons = "; ".join(_esc(r) for r in candidate.exclusion_reasons) or "&mdash;"
        site = (
            f'<a href="{_esc(candidate.website)}" rel="noopener">site</a>'
            if candidate.website
            else "&mdash;"
        )
        rows.append(
            f"<tr><td>{_esc(candidate.kennel)}</td>"
            f"<td>{_esc(candidate.region or '??')}</td>"
            f"<td>{candidate.score:g}</td>"
            f"<td>{reasons}</td><td>{site}</td></tr>"
        )
    return (
        '<div class="scroll"><table><thead><tr><th>Kennel</th><th>State</th>'
        "<th>Score</th><th>What is missing</th><th></th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )


def render_html(run: ProtocolRun) -> str:
    shortlist = (
        "".join(
            _candidate_card(c, rank=i) for i, c in enumerate(run.shortlist, start=1)
        )
        or '<p class="empty">No kennel cleared all three stages in this run. '
        "Read the funnel above and the near misses below before concluding that "
        "none exists: a zero here is as likely to mean a source did not parse "
        "as it is to mean the bar is empty.</p>"
    )
    confirm = (
        "".join(_candidate_card(c) for c in run.needs_confirmation)
        or '<p class="empty">No ambiguous registry joins in this run.</p>'
    )
    notes = "".join(f"<li>{_esc(n)}</li>" for n in run.notes) or "<li>none</li>"

    banner = ""
    if run.sample_data:
        banner = (
            '<div class="sample"><strong>Sample data, not real breeders.</strong> '
            "This report was generated from the bundled test fixtures to show "
            "the pipeline working. Every kennel, contact, credential and health "
            "result below is invented, and the websites use the reserved "
            "<code>.example</code> domain. Nothing here describes an actual "
            "breeding program. Run <code>python3 -m doodle_scout run</code> "
            "without <code>--selftest</code> for real results.</div>"
        )

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Standard ALD Breeder Shortlist</title>
<meta name="description" content="ALAA Platinum crossed with WALA rating, filtered to standard-size Australian Labradoodle programs.">
<style>{CSS}</style>
</head><body><div class="wrap">

{banner}
<h1>Standard Australian Labradoodle breeder shortlist</h1>
<p class="sub">Run {_esc(run.started_at)} &rarr; {_esc(run.finished_at)}.
Every claim below links to the page it came from. Registry status changes, so
re-run before you send a deposit.</p>

<h2>The funnel</h2>
{_funnel(run)}

<h2>Shortlist</h2>
{shortlist}

<h2>Needs your confirmation</h2>
<p class="sub">These kennels matched across the two registries on name and
state, but not on a website domain, phone or email. Confirm the pairing is
one kennel and not two before trusting the combined credentials.</p>
{confirm}

<h2>Near misses</h2>
<p class="sub">Cleared some of the protocol but not all of it. Worth reading:
a Platinum breeder who simply is not a WALA member is not a worse breeder,
and this is where most of the real choice lives.</p>
{_near_miss_table(run.near_misses)}

<h2>What this cannot tell you</h2>
<div class="panel caveat">
<p><strong>Appearance is not scored anywhere in this tool.</strong> Coat type,
structure and expression cannot be read off a registry listing, and a number
invented for them would look like evidence while carrying none. Use the
adult-dog links on each card and judge with your own eyes. Ask for photos of
both parents as adults; puppy photos tell you nothing about how a coat
matures.</p>
<p><strong>Temperament is only indirectly covered.</strong> ALAA Platinum is a
hip and elbow testing award. WALA Diamond adds testing breadth and breeder
education. Neither certifies that a puppy was raised well. The rearing signals
on each card are read off the breeder's own marketing copy, which means they
record a claim, not a verified practice. Confirm them by visiting.</p>
<p><strong>Both registries are membership organizations</strong> that act on
paperwork members submit. The OFA link on each card checks the hip and elbow
clearances against the primary public record instead. That is the only step
here that does not require trusting a registry.</p>
</div>

<h2>Run detail</h2>
<details><summary>Sources, warnings and every request made ({len(run.notes)})</summary>
<ul>{notes}</ul></details>

</div></body></html>
"""


def write_outputs(run: ProtocolRun, out_dir: Path) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    html_path = out_dir / "shortlist.html"
    html_path.write_text(render_html(run), encoding="utf-8")
    written["html"] = html_path

    json_path = out_dir / "shortlist.json"
    json_path.write_text(
        json.dumps(
            {
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "sample_data": run.sample_data,
                "funnel": run.funnel,
                "shortlist": [to_jsonable(c) for c in run.shortlist],
                "needs_confirmation": [to_jsonable(c) for c in run.needs_confirmation],
                "near_misses": [to_jsonable(c) for c in run.near_misses],
                "notes": run.notes,
                "config": run.config_snapshot,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    written["json"] = json_path

    csv_path = out_dir / "shortlist.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["rank", "kennel", "city", "state", "score", "alaa_awards",
             "wala_awards", "size_verdict", "size_confidence", "match_status",
             "website", "email", "phone", "followups"]
        )
        for index, candidate in enumerate(run.shortlist, start=1):
            writer.writerow([
                index,
                candidate.kennel,
                candidate.city,
                candidate.region,
                candidate.score,
                "; ".join(candidate.alaa_awards),
                "; ".join(candidate.wala_awards),
                candidate.size.verdict.value,
                candidate.size.confidence.value,
                candidate.match.status,
                candidate.website,
                (candidate.alaa.email if candidate.alaa else "")
                or (candidate.wala.email if candidate.wala else ""),
                (candidate.alaa.phone if candidate.alaa else "")
                or (candidate.wala.phone if candidate.wala else ""),
                " | ".join(candidate.followups),
            ])
    written["csv"] = csv_path
    return written
