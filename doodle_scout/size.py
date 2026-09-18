"""Stage 3 of the protocol: is this a standard-size program?

Neither registry exposes a reliable size filter, so size has to be read off
the breeder's own pages. The word "standard" is treacherous in this corpus:

  "the ALAA breed standard"   -> a document, not a size
  "standard poodle"           -> a parent breed, not the labradoodle
  "our standard contract"     -> boilerplate
  "standards and mediums"     -> what we actually want

So a "standard" mention only counts when it sits in a size context, and
never when it is part of "breed standard" or "standard poodle". Anything
unresolved comes back UNKNOWN and is kept for the human to confirm rather
than silently dropped, because dropping a program by mistake could discard
the best breeder on the list.
"""

from __future__ import annotations

import re

from .models import Confidence, Evidence, SizeAssessment, SizeVerdict

STANDARD_WORD = re.compile(r"\bstandards?\b", re.I)

# "we breed standard size dogs" (a size) vs "the ALAA breed standard" (a
# document). Both put "breed" immediately before "standard", so the
# disambiguator is what comes after.
BREED_BEFORE = re.compile(r"\bbreeds?\s+$", re.I)
SIZE_FOLLOWER = re.compile(
    r"^\s*(?:size[sd]?|and|or|&|/|australian|labradoodles?|doodles?|alds?|"
    r"puppies|puppy|dogs?|litters?|girls?|boys?|males?|females?|,?\s*\d{2})",
    re.I,
)
# Words that turn "standard" into boilerplate rather than a dog size.
NON_SIZE_FOLLOWER = re.compile(
    r"^\s*(?:poodles?|contracts?|deposits?|agreements?|policy|policies|"
    r"practice|procedures?|protocols?|fees?|guarantees?|warrant\w*|"
    r"shipping|delivery|testing|tests?|vaccinations?|vetting|paperwork|"
    r"process|pricing|price|terms?|of\s+care|operating)",
    re.I,
)

# A "standard" mention only counts as a size claim if at least one of these
# corroborates it nearby. Requiring positive evidence beats blacklisting
# boilerplate, because boilerplate is open-ended ("standard health testing",
# "standard two-year guarantee", "standard vetting") and size vocabulary
# is not.
SIZE_NOUN_NEAR = re.compile(r"\bsize[sd]?\b", re.I)
CATEGORY_NEAR = re.compile(
    r"\b(?:mini|minis|miniature|miniatures|medium|mediums|petite|toy)\b", re.I
)
BREED_NOUN_AFTER = re.compile(
    r"^\s*(?:australian\s+)?(?:labradoodles?|doodles?|alds?|"
    r"(?:girls?|boys?|males?|females?|dogs?|puppies|puppy|adults?))\b",
    re.I,
)
MEASURE_NEAR = re.compile(
    r"\d{2}\s*(?:-|to|\u2013|\u2014)\s*\d{2,3}\s*"
    r"(?:in\b|inch|inches|\"|\u201d|lb|lbs|pound)",
    re.I,
)

MEDIUM_WORD = re.compile(r"\bmedium(?:s|\ssize[ds]?)?\b", re.I)
MINI_WORD = re.compile(r"\b(?:mini|minis|miniature|miniatures|petite|toy)\b", re.I)

EXCLUSIONS = (
    re.compile(r"\b(?:we\s+)?(?:do\s+not|don'?t|no\s+longer)\s+breed[^.]{0,40}standard", re.I),
    re.compile(r"\bstandards?\s+are\s+not\s+(?:a\s+)?(?:part|available)", re.I),
    re.compile(r"\b(?:mini|miniature|medium)s?\s+(?:and|&|/|or)\s+(?:mini|miniature|medium)s?\s+(?:sizes?\s+)?only\b", re.I),
    re.compile(r"\bonly\s+(?:breed\s+)?(?:mini|miniature|medium)s?\s+(?:and|&|/|or)\s+(?:mini|miniature|medium)s?\b", re.I),
    re.compile(r"\bwe\s+(?:only\s+)?breed\s+(?:mini|miniature|medium)s?(?:\s+(?:and|&|/|or)\s+(?:mini|miniature|medium)s?)?\s+(?:size[sd]?\s+)?only\b", re.I),
)

HEIGHT_RANGE = re.compile(
    r"(\d{2})\s*(?:-|to|–|—)\s*(\d{2})\s*(?:in\b|inch|inches|\"|”)", re.I
)
WEIGHT_RANGE = re.compile(
    r"(\d{2})\s*(?:-|to|–|—)\s*(\d{2,3})\s*(?:lb|lbs|pound)", re.I
)


def _quote(text: str, start: int, end: int, pad: int = 90) -> str:
    lo = max(0, start - pad)
    hi = min(len(text), end + pad)
    return " ".join(text[lo:hi].split())


def _size_claims(text: str) -> list[tuple[int, int]]:
    """Positions of 'standard' mentions that really mean the dog size."""
    out = []
    for match in STANDARD_WORD.finditer(text):
        before = text[max(0, match.start() - 24) : match.start()]
        after = text[match.end() : match.end() + 40]

        if NON_SIZE_FOLLOWER.match(after):
            continue
        if BREED_BEFORE.search(before) and not SIZE_FOLLOWER.match(after):
            continue

        near_40 = text[max(0, match.start() - 40) : match.end() + 40]
        near_60 = text[max(0, match.start() - 60) : match.end() + 60]
        corroborated = (
            SIZE_NOUN_NEAR.search(near_40)
            or BREED_NOUN_AFTER.match(after)
            or CATEGORY_NEAR.search(near_40)
            or MEASURE_NEAR.search(near_60)
        )
        if corroborated:
            out.append((match.start(), match.end()))
    return out


def _overlaps(low: int, high: int, target: tuple[int, int]) -> bool:
    return not (high < target[0] or low > target[1])


def classify(documents: list[tuple[str, str]], config) -> SizeAssessment:
    """documents is [(source_url, text), ...]."""
    std_range = config.get("breed_standard.standard", {}) or {}
    height_target = (int(std_range.get("min_in", 21)), int(std_range.get("max_in", 24)))
    weight_target = tuple(std_range.get("weight_lb", [50, 65]))

    evidence: list[Evidence] = []
    sizes_seen: set[str] = set()
    excluded_by = None
    standard_claims = 0
    measurement_support = False

    for url, text in documents:
        if not text:
            continue
        flat = " ".join(text.split())

        for pattern in EXCLUSIONS:
            match = pattern.search(flat)
            if match:
                excluded_by = Evidence(
                    claim="program states it does not breed standards",
                    quote=_quote(flat, match.start(), match.end()),
                    source_url=url,
                )
                break

        for start, end in _size_claims(flat):
            standard_claims += 1
            sizes_seen.add("Standard")
            if len(evidence) < 12:
                evidence.append(
                    Evidence(
                        claim="standard size mentioned in a size context",
                        quote=_quote(flat, start, end),
                        source_url=url,
                    )
                )

        if MEDIUM_WORD.search(flat):
            sizes_seen.add("Medium")
        if MINI_WORD.search(flat):
            sizes_seen.add("Miniature")

        for match in HEIGHT_RANGE.finditer(flat):
            low, high = int(match.group(1)), int(match.group(2))
            if low <= high and _overlaps(low, high, height_target):
                measurement_support = True
                if len(evidence) < 14:
                    evidence.append(
                        Evidence(
                            claim=f"height range {low}-{high} in overlaps the "
                            f"standard band {height_target[0]}-{height_target[1]} in",
                            quote=_quote(flat, match.start(), match.end()),
                            source_url=url,
                        )
                    )

        for match in WEIGHT_RANGE.finditer(flat):
            low, high = int(match.group(1)), int(match.group(2))
            if low <= high and _overlaps(low, high, weight_target):
                measurement_support = True
                if len(evidence) < 16:
                    evidence.append(
                        Evidence(
                            claim=f"weight range {low}-{high} lb overlaps the "
                            f"standard band {weight_target[0]}-{weight_target[1]} lb",
                            quote=_quote(flat, match.start(), match.end()),
                            source_url=url,
                        )
                    )

    if excluded_by is not None:
        # The word "standard" appearing inside "no standards available" is
        # not a size this program offers.
        sizes_seen.discard("Standard")
        return SizeAssessment(
            verdict=SizeVerdict.STANDARD_EXCLUDED,
            confidence=Confidence.HIGH,
            sizes_seen=sorted(sizes_seen),
            evidence=[excluded_by] + evidence[:4],
        )

    if standard_claims and measurement_support:
        verdict, confidence = SizeVerdict.STANDARD_CONFIRMED, Confidence.HIGH
    elif standard_claims >= 2:
        verdict, confidence = SizeVerdict.STANDARD_CONFIRMED, Confidence.MEDIUM
    elif standard_claims == 1:
        verdict, confidence = SizeVerdict.STANDARD_LIKELY, Confidence.MEDIUM
    elif sizes_seen and "Standard" not in sizes_seen:
        verdict, confidence = SizeVerdict.STANDARD_UNLIKELY, Confidence.LOW
    else:
        verdict, confidence = SizeVerdict.UNKNOWN, Confidence.NONE

    return SizeAssessment(
        verdict=verdict,
        confidence=confidence,
        sizes_seen=sorted(sizes_seen),
        evidence=evidence[:8],
    )
