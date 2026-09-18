"""The funnel.

  Stage 1  ALAA member list, filtered to Platinum Paw   (authoritative list)
  Stage 2  cross-filtered against WALA ratings          (second rule set)
  Stage 3  cross-filtered to standard-size programs     (tightest constraint)

Two things this module insists on. First, the count at every stage is
recorded, because "how much did this cut the list" is most of the value and
a silently empty result has to be distinguishable from a genuinely empty
one. Second, near misses are kept. A filter this strict can leave almost
nobody, and the breeders who clear two of three bars are the real decision
surface, not noise.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .http_client import HttpClient
from .models import (
    Candidate,
    Confidence,
    SizeAssessment,
    SizeVerdict,
    utc_now,
)
from .resolve import resolve
from .score import score_candidate
from .size import classify
from .sources import alaa as alaa_source
from .sources import breeder_site
from .sources import ofa as ofa_source
from .sources import wala as wala_source


@dataclass
class ProtocolRun:
    started_at: str = field(default_factory=utc_now)
    finished_at: str = ""
    funnel: list[dict] = field(default_factory=list)
    shortlist: list[Candidate] = field(default_factory=list)
    near_misses: list[Candidate] = field(default_factory=list)
    needs_confirmation: list[Candidate] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    config_snapshot: dict = field(default_factory=dict)
    sample_data: bool = False

    def stage(self, name: str, description: str, count: int, detail: str = "") -> None:
        self.funnel.append(
            {
                "stage": name,
                "description": description,
                "remaining": count,
                "detail": detail,
            }
        )


def load_manual_overlay(path: Path) -> dict:
    """User-maintained facts the tool cannot establish on its own.

    Keyed by lowercased kennel name, e.g.
      {"quillfeather labradoodles": {"ofa_verified": true, "notes": "spoke 9/14"}}
    """
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(raw, dict):
        return {}
    # The file is hand-edited, so tolerate comment keys and stray scalars
    # rather than failing a whole run over a typo.
    return {
        str(key).strip().lower(): value
        for key, value in raw.items()
        if isinstance(value, dict) and not str(key).startswith("_")
    }


def _award_matches(awards: list[str], accepted: list[str]) -> str:
    """Return the matching accepted award label, or ''."""
    lowered = [a.lower() for a in awards]
    for want in accepted:
        for award in lowered:
            if award.startswith(want.lower()):
                return want
    return ""


def run(
    client: HttpClient,
    config,
    *,
    alaa_saved_dir: Path | None = None,
    wala_saved_dir: Path | None = None,
    manual_path: Path | None = None,
    read_sites: bool = True,
    regions: list[str] | None = None,
    site_page_budget: int = 7,
    sample_data: bool = False,
) -> ProtocolRun:
    run_result = ProtocolRun(config_snapshot=config.raw, sample_data=sample_data)
    manual = load_manual_overlay(manual_path) if manual_path else {}

    # ---- Stage 1: ALAA, filtered to Platinum --------------------------
    alaa_records, alaa_notes = alaa_source.collect(
        client, config, alaa_saved_dir, regions=regions
    )
    run_result.notes.extend(alaa_notes)
    run_result.stage(
        "0. ALAA member breeders",
        "Every current ALAA member breeder found (the authoritative list, "
        "regenerated every 24 hours).",
        len(alaa_records),
    )

    accepted_paws = config.get("protocol.stage_1_alaa.accepted_awards", ["Platinum"])
    if config.get("protocol.stage_1_alaa.enabled", True):
        platinum = [
            r for r in alaa_records if _award_matches(r.awards, accepted_paws)
        ]
    else:
        platinum = list(alaa_records)
    run_result.stage(
        "1. ALAA Platinum Paw",
        f"Holding {' or '.join(accepted_paws)} Paw. This is a hip/elbow "
        "health-testing award, not a general breeder tier.",
        len(platinum),
    )

    # ---- Stage 2: cross-filter against WALA ---------------------------
    wala_records, wala_notes = wala_source.collect(client, config, wala_saved_dir)
    run_result.notes.extend(wala_notes)

    resolution = resolve(platinum, wala_records, config)
    run_result.notes.extend(resolution.notes)

    accepted_ratings = config.get("protocol.stage_2_wala.accepted_ratings", [])
    legacy_ratings = config.get("protocol.stage_2_wala.legacy_ratings", [])
    accept_legacy = config.get("protocol.stage_2_wala.accept_legacy_as_pass", True)
    wala_enabled = config.get("protocol.stage_2_wala.enabled", True)

    candidates: list[Candidate] = []
    confirm: list[Candidate] = []
    for alaa_record, wala_record, match in resolution.pairs:
        rating = _award_matches(wala_record.awards, accepted_ratings)
        legacy = _award_matches(wala_record.awards, legacy_ratings)
        candidate = Candidate(
            kennel=alaa_record.kennel or wala_record.kennel,
            alaa=alaa_record,
            wala=wala_record,
            match=match,
        )
        candidate.stage_results["alaa_platinum"] = True
        passes_wala = bool(rating) or (accept_legacy and bool(legacy))
        candidate.stage_results["wala_rating"] = passes_wala or not wala_enabled
        if legacy and not rating:
            candidate.followups.append(
                "WALA rating on file is the legacy 'All Star' from the retired "
                "Star Rewards Program. Ask the breeder for their current "
                "Diamond level."
            )
        if not passes_wala and wala_enabled:
            candidate.exclusion_reasons.append(
                "matched to a WALA listing but with no accepted rating "
                f"(found: {wala_record.awards or 'none'})"
            )
        if match.status == "review":
            confirm.append(candidate)
        else:
            candidates.append(candidate)

    # Platinum breeders with no WALA listing at all are near misses, not
    # failures: WALA membership is a separate choice, not a quality verdict.
    for alaa_record in resolution.alaa_only:
        candidate = Candidate(kennel=alaa_record.kennel, alaa=alaa_record)
        candidate.stage_results["alaa_platinum"] = True
        candidate.stage_results["wala_rating"] = not wala_enabled
        candidate.exclusion_reasons.append(
            "no WALA listing matched. Either not a WALA member, or listed "
            "under a name this tool could not join."
        )
        candidates.append(candidate)

    passing_stage_2 = [c for c in candidates if c.stage_results.get("wala_rating")]
    run_result.stage(
        "2. WALA rating (cross-filter)",
        "Also holds a current WALA Diamond rating"
        + (", or the retired All Star title" if accept_legacy else "")
        + ". Two independent rule sets at once.",
        len(passing_stage_2),
        detail=f"{len(confirm)} further pairing(s) need your confirmation.",
    )

    # ---- Stage 3: standard size ---------------------------------------
    target_sizes = config.get("protocol.stage_3_size.target_sizes", ["Standard"])
    keep_unknown = config.get("protocol.stage_3_size.keep_unknown_for_review", True)
    size_enabled = config.get("protocol.stage_3_size.enabled", True)

    to_read = passing_stage_2 + confirm
    for candidate in to_read:
        site_signals: dict = {}
        documents: list[tuple[str, str]] = []
        if read_sites and candidate.website:
            documents, site_notes = breeder_site.read_site(
                client, candidate.website, max_pages=site_page_budget
            )
            for note in site_notes:
                run_result.notes.append(f"{candidate.kennel}: {note}")
            site_signals = breeder_site.detect_signals(documents)
            candidate.size = classify(documents, config)
        elif not candidate.website:
            candidate.size = SizeAssessment(
                verdict=SizeVerdict.UNKNOWN,
                confidence=Confidence.NONE,
            )
            candidate.followups.append(
                "No website in either registry. Size and rearing practice "
                "have to be asked directly."
            )
        else:
            candidate.followups.append("Site reading skipped (--no-sites).")

        if size_enabled:
            verdict = candidate.size.verdict
            if verdict in (SizeVerdict.STANDARD_CONFIRMED, SizeVerdict.STANDARD_LIKELY):
                candidate.stage_results["standard_size"] = True
            elif verdict == SizeVerdict.UNKNOWN and keep_unknown:
                candidate.stage_results["standard_size"] = True
                candidate.followups.append(
                    "Size not stated anywhere this tool could read. Confirm "
                    "they breed standards before anything else."
                )
            else:
                candidate.stage_results["standard_size"] = False
                candidate.exclusion_reasons.append(
                    f"size assessment: {verdict.value}"
                )
        else:
            candidate.stage_results["standard_size"] = True

        candidate.verification_links = ofa_source.verification_links(
            candidate.kennel,
            ofa_search_url=config.get(
                "sources.ofa_search_url", "https://ofa.org/advanced-search/"
            ),
            alaa_detail_url=candidate.alaa.detail_url if candidate.alaa else "",
            wala_url=candidate.wala.detail_url if candidate.wala else "",
            website=candidate.website,
        )
        photo_pages = breeder_site.adult_photo_pages(documents)
        for index, url in enumerate(photo_pages[:3], start=1):
            candidate.verification_links[f"Adult dogs, page {index}"] = url
        if not photo_pages and documents:
            candidate.followups.append(
                "No adult-dog page found. Ask for photos of both parents as "
                "adults; puppy photos say nothing about coat or structure."
            )

        score_candidate(
            candidate, config, site_signals, manual.get(candidate.kennel.lower())
        )

    shortlist = [c for c in passing_stage_2 if c.passed]
    shortlist.sort(key=lambda c: -c.score)
    near = [c for c in candidates if not c.passed]
    near.sort(key=lambda c: -c.score)
    confirm.sort(key=lambda c: -c.score)

    run_result.stage(
        "3. Standard-size program",
        "Breeds standards. Most ALD programs are mini and medium, so this "
        "is the tightest constraint in the protocol.",
        len(shortlist),
    )

    excluded = {k.strip().lower() for k, v in manual.items() if v.get("exclude")}
    if excluded:
        before = len(shortlist)
        shortlist = [c for c in shortlist if c.kennel.lower() not in excluded]
        run_result.notes.append(
            f"Manual overlay excluded {before - len(shortlist)} kennel(s)."
        )

    run_result.shortlist = shortlist
    run_result.near_misses = near[:40]
    run_result.needs_confirmation = confirm
    run_result.finished_at = utc_now()
    run_result.notes.extend(
        f"HTTP: {entry['url']} -> {entry['outcome']}" for entry in client.request_log[-40:]
    )
    return run_result
