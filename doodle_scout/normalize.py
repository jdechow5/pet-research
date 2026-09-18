"""Normalization helpers for joining two registries that share no key.

ALAA and WALA maintain independent member lists with independent IDs. To
cross-filter one against the other we have to decide when "Quillfeather"
and "Quillfeather Australian Labradoodles, LLC" are the same kennel, and
when "Willow Creek" (OR) and "Willow Creek" (VA) are not.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from urllib.parse import urlsplit

# Tokens that carry almost no identifying information in this breed's
# kennel names. Stripped only to generate match candidates, never for
# display, and never for the final similarity score.
GENERIC_TOKENS = {
    "a", "an", "and", "at", "the", "of", "on", "by",
    "australian", "aussie", "australia",
    "labradoodle", "labradoodles", "labradoodel", "doodle", "doodles",
    "lab", "labs", "retriever", "poodle", "poodles",
    "kennel", "kennels", "cattery",
    "llc", "lc", "inc", "incorporated", "co", "corp", "company", "ltd", "dba",
    "breeder", "breeders", "breeding", "program", "programs",
    "puppy", "puppies", "pup", "pups", "dog", "dogs",
    "reg", "registered", "certified",
    "usa", "us", "america", "american",
}

# Multi-label public suffixes we are likely to meet. Not exhaustive; the
# fallback is the last two labels, which is right for .com/.net/.org.
MULTI_SUFFIXES = {
    "co.uk", "org.uk", "me.uk", "ltd.uk", "plc.uk", "net.uk", "sch.uk",
    "com.au", "net.au", "org.au", "id.au", "asn.au",
    "co.nz", "net.nz", "org.nz",
    "co.za", "org.za",
    "com.br", "com.mx", "com.ar", "co.jp", "or.jp", "ne.jp",
    "co.in", "com.sg", "com.hk", "com.tw", "co.il",
}

US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT",
    "delaware": "DE", "district of columbia": "DC", "florida": "FL",
    "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
    "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY",
    "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT",
    "nebraska": "NE", "nevada": "NV", "new hampshire": "NH",
    "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}

CA_PROVINCES = {
    "alberta": "AB", "british columbia": "BC", "manitoba": "MB",
    "new brunswick": "NB", "newfoundland and labrador": "NL",
    "nova scotia": "NS", "ontario": "ON", "prince edward island": "PE",
    "quebec": "QC", "québec": "QC", "saskatchewan": "SK",
}

REGION_CODES = set(US_STATES.values()) | set(CA_PROVINCES.values())

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_DIGITS = re.compile(r"\d")


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def slug(value: str) -> str:
    """Lowercase, accent-free, alphanumeric-and-single-space form."""
    if not value:
        return ""
    value = strip_accents(value).lower()
    value = value.replace("&", " and ").replace("+", " and ")
    value = _NON_ALNUM.sub(" ", value)
    return " ".join(value.split())


def tokens(value: str) -> list[str]:
    return slug(value).split()


def core_tokens(value: str) -> list[str]:
    """Distinctive tokens only. Falls back to all tokens if stripping
    would leave nothing (e.g. a kennel literally named "The Labradoodles")."""
    all_tokens = tokens(value)
    kept = [t for t in all_tokens if t not in GENERIC_TOKENS]
    return kept or all_tokens


def blocking_keys(value: str) -> set[str]:
    """Cheap keys used to pull candidate matches out of an index.

    Recall matters far more than precision here; scoring does the real work.
    """
    core = core_tokens(value)
    keys = set()
    if not core:
        return keys
    keys.add(" ".join(sorted(core)))
    for token in core:
        if len(token) >= 4:
            keys.add(token)
            keys.add(token[:5])
    return keys


def registrable_domain(url_or_host: str) -> str:
    """eTLD+1, lowercase, no www. The strongest join key we have, because
    both registries publish breeder websites."""
    if not url_or_host:
        return ""
    raw = url_or_host.strip()
    if "//" not in raw:
        raw = "//" + raw
    host = (urlsplit(raw).hostname or "").lower().strip(".")
    if not host or "." not in host:
        return ""
    for prefix in ("www.", "www2.", "m."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    labels = host.split(".")
    if len(labels) < 2:
        return ""
    last_two = ".".join(labels[-2:])
    if last_two in MULTI_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return last_two


def region_code(value: str) -> str:
    """Normalize a state/province to its 2-letter code, or ''."""
    if not value:
        return ""
    raw = value.strip()
    upper = raw.upper()
    if len(upper) == 2 and upper in REGION_CODES:
        return upper
    key = slug(raw)
    if key in US_STATES:
        return US_STATES[key]
    if key in CA_PROVINCES:
        return CA_PROVINCES[key]
    # "Portland, OR" / "Bend OR 97701"
    match = re.search(r"\b([A-Z]{2})\b(?:\s+\d{5})?\s*$", raw.upper())
    if match and match.group(1) in REGION_CODES:
        return match.group(1)
    for name, code in {**US_STATES, **CA_PROVINCES}.items():
        if re.search(rf"\b{re.escape(name)}\b", key):
            return code
    return ""


def phone_digits(value: str) -> str:
    """Last 10 digits, so formatting and +1 prefixes stop mattering."""
    digits = "".join(_DIGITS.findall(value or ""))
    if len(digits) >= 10:
        return digits[-10:]
    return ""


def email_key(value: str) -> str:
    value = (value or "").strip().lower()
    return value if "@" in value and "." in value.split("@")[-1] else ""


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def name_similarity(left: str, right: str) -> float:
    """0..1 similarity between two kennel names.

    Blends token overlap (robust to word order and to a dropped "LLC")
    with character-level ratio (robust to plurals and small misspellings).
    """
    left_core, right_core = core_tokens(left), core_tokens(right)
    if not left_core or not right_core:
        return 0.0

    joined_left, joined_right = "".join(left_core), "".join(right_core)
    # "Harrow Gate" and "Harrowgate" are the same kennel spelled two ways.
    # Token overlap scores that at zero, so check the concatenation first.
    if joined_left == joined_right:
        return 1.0

    token_score = jaccard(set(left_core), set(right_core))
    char_score = difflib.SequenceMatcher(None, joined_left, joined_right).ratio()
    blended = 0.6 * token_score + 0.4 * char_score

    # Full containment ("Quillfeather" inside "Quillfeather Australian
    # Labradoodles") is strong evidence that token Jaccard under-credits,
    # because the extra tokens are the generic ones.
    if set(left_core) <= set(right_core) or set(right_core) <= set(left_core):
        boost = 0.5 + 0.5 * char_score
        # One shared distinctive token is not enough to auto-join: "Willow"
        # sits inside "Willow Creek" and "Willow Ridge" alike. Cap it below
        # the auto-accept threshold so a human confirms.
        if min(len(left_core), len(right_core)) == 1:
            boost = min(boost, 0.88)
        blended = max(blended, boost)

    return round(min(blended, 1.0), 4)
