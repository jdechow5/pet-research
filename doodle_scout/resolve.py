"""Cross-registry entity resolution.

ALAA and WALA assign their own ids and share no common key, so the only way
to cross-filter one against the other is to decide which listings describe
the same kennel. Getting this wrong in the permissive direction would credit
a breeder with a credential they do not hold, which is the worst failure
this tool could produce. So:

  * a shared website domain, phone or email is treated as near-proof;
  * a name-only match must also agree on state;
  * anything in the middle band is surfaced for human confirmation rather
    than asserted.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import BreederRecord, MatchInfo
from .normalize import blocking_keys, email_key, name_similarity, phone_digits


@dataclass
class ResolveResult:
    pairs: list[tuple[BreederRecord, BreederRecord, MatchInfo]] = field(
        default_factory=list
    )
    alaa_only: list[BreederRecord] = field(default_factory=list)
    wala_only: list[BreederRecord] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def matched(self):
        return [p for p in self.pairs if p[2].status == "matched"]

    @property
    def review(self):
        return [p for p in self.pairs if p[2].status == "review"]


class _Index:
    def __init__(self, records: list[BreederRecord]):
        self.by_domain: dict[str, list[BreederRecord]] = {}
        self.by_block: dict[str, list[BreederRecord]] = {}
        self.by_phone: dict[str, list[BreederRecord]] = {}
        self.by_email: dict[str, list[BreederRecord]] = {}
        for record in records:
            if record.domain:
                self.by_domain.setdefault(record.domain, []).append(record)
            for key in blocking_keys(record.kennel):
                self.by_block.setdefault(key, []).append(record)
            phone = phone_digits(record.phone)
            if phone:
                self.by_phone.setdefault(phone, []).append(record)
            email = email_key(record.email)
            if email:
                self.by_email.setdefault(email, []).append(record)

    def candidates(self, record: BreederRecord) -> list[BreederRecord]:
        out: dict[int, BreederRecord] = {}
        buckets = []
        if record.domain:
            buckets.append(self.by_domain.get(record.domain, []))
        phone = phone_digits(record.phone)
        if phone:
            buckets.append(self.by_phone.get(phone, []))
        email = email_key(record.email)
        if email:
            buckets.append(self.by_email.get(email, []))
        for key in blocking_keys(record.kennel):
            buckets.append(self.by_block.get(key, []))
        for bucket in buckets:
            for candidate in bucket:
                out[id(candidate)] = candidate
        return list(out.values())


def score_pair(
    alaa: BreederRecord, wala: BreederRecord, config
) -> tuple[float, list[str]]:
    """Return (score, basis) for one candidate pairing."""
    basis: list[str] = []
    score = name_similarity(alaa.kennel, wala.kennel)
    if score > 0:
        basis.append(f"kennel name similarity {score:.2f}")

    if alaa.domain and alaa.domain == wala.domain:
        score = 1.0
        basis.insert(0, f"same website domain ({alaa.domain})")

    alaa_phone, wala_phone = phone_digits(alaa.phone), phone_digits(wala.phone)
    if alaa_phone and alaa_phone == wala_phone:
        score = max(score, 0.95)
        basis.append("same phone number")

    alaa_email, wala_email = email_key(alaa.email), email_key(wala.email)
    if alaa_email and alaa_email == wala_email:
        score = max(score, 0.95)
        basis.append("same email address")

    if alaa.region and wala.region:
        if alaa.region == wala.region:
            score = min(1.0, score + 0.05)
            basis.append(f"state agrees ({alaa.region})")
        else:
            penalty = float(config.get("matching.region_mismatch_penalty", 0.35))
            score = max(0.0, score - penalty)
            basis.append(f"state disagrees ({alaa.region} vs {wala.region})")

    return round(score, 4), basis


def resolve(
    alaa_records: list[BreederRecord],
    wala_records: list[BreederRecord],
    config,
) -> ResolveResult:
    auto = float(config.get("matching.auto_accept", 0.90))
    floor = float(config.get("matching.review_floor", 0.72))
    require_region = bool(config.get("matching.require_region_agreement", True))

    index = _Index(alaa_records)
    result = ResolveResult()
    claimed: dict[int, tuple[float, BreederRecord]] = {}
    raw_pairs: list[tuple[BreederRecord, BreederRecord, MatchInfo]] = []
    matched_wala: set[int] = set()

    for wala in wala_records:
        scored = []
        for alaa in index.candidates(wala):
            score, basis = score_pair(alaa, wala, config)
            if score >= floor:
                scored.append((score, basis, alaa))
        if not scored:
            continue
        scored.sort(key=lambda item: -item[0])
        score, basis, alaa = scored[0]

        name_only = not any(
            b.startswith(("same website", "same phone", "same email")) for b in basis
        )
        region_known = bool(alaa.region and wala.region)
        region_agrees = region_known and alaa.region == wala.region

        status = "matched" if score >= auto else "review"
        if status == "matched" and name_only and require_region and not region_agrees:
            status = "review"
            basis.append(
                "name-only match without agreeing state: needs confirmation"
            )

        info = MatchInfo(
            score=score,
            basis=basis,
            status=status,
            runners_up=[
                f"{other.kennel} ({other.region or '??'}) @ {other_score:.2f}"
                for other_score, _, other in scored[1:4]
            ],
        )
        raw_pairs.append((alaa, wala, info))
        matched_wala.add(id(wala))

        # One-to-one enforcement: if two WALA records claim the same ALAA
        # listing, only the stronger keeps "matched".
        previous = claimed.get(id(alaa))
        if previous is None or score > previous[0]:
            claimed[id(alaa)] = (score, wala)

    for alaa, wala, info in raw_pairs:
        winner = claimed.get(id(alaa))
        if winner and winner[1] is not wala and info.status == "matched":
            info.status = "review"
            info.basis.append(
                f"another WALA listing ({winner[1].kennel}) matched this ALAA "
                f"record more strongly at {winner[0]:.2f}"
            )
            result.notes.append(
                f"Two WALA listings competed for ALAA record "
                f"'{alaa.kennel}': kept '{winner[1].kennel}', flagged "
                f"'{wala.kennel}' for review."
            )
        result.pairs.append((alaa, wala, info))

    paired_alaa = {id(p[0]) for p in result.pairs if p[2].status == "matched"}
    result.alaa_only = [r for r in alaa_records if id(r) not in paired_alaa]
    result.wala_only = [r for r in wala_records if id(r) not in matched_wala]

    result.notes.append(
        f"Resolution: {len(result.matched)} confident match(es), "
        f"{len(result.review)} needing confirmation, "
        f"{len(result.alaa_only)} ALAA-only, {len(result.wala_only)} WALA-only."
    )
    return result
