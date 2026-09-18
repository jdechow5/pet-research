"""Independent verification links.

Both ALAA and WALA are membership organizations that award status on the
basis of paperwork their members submit. The Orthopedic Foundation for
Animals is not: its database is the primary record for hip, elbow, eye and
cardiac clearances, and it is public. So a Platinum Paw claim is checkable
against OFA directly, which is the one step in this whole process that does
not depend on trusting a registry.

This module builds the exact links to run those checks. It deliberately
does not scrape OFA and then assert a result: the search needs the names of
the individual breeding dogs, which come off the breeder's own site, and a
wrong automated read here would be worse than no read at all.
"""

from __future__ import annotations

from urllib.parse import quote_plus


def verification_links(
    kennel: str,
    *,
    ofa_search_url: str = "https://ofa.org/advanced-search/",
    alaa_detail_url: str = "",
    wala_url: str = "",
    website: str = "",
) -> dict[str, str]:
    """Click-through checks for one kennel, in the order worth doing them."""
    name = (kennel or "").strip()
    links: dict[str, str] = {}

    if alaa_detail_url:
        links["ALAA listing (confirm Platinum today)"] = alaa_detail_url
    if wala_url:
        links["WALA listing (confirm current rating)"] = wala_url
    links["OFA advanced search (paste each breeding dog's registered name)"] = (
        ofa_search_url
    )
    if name:
        links["OFA records mentioning this kennel"] = (
            "https://www.google.com/search?q="
            + quote_plus(f'site:ofa.org "{name}"')
        )
    if website:
        links["Breeder site"] = website
    return links


def dog_name_candidates(documents: list[tuple[str, str]]) -> list[str]:
    """Best-effort list of registered-looking dog names found on a site.

    Registered Australian Labradoodle names usually lead with the kennel
    prefix, e.g. "Draycot Meadows Winter Song". This is a starting list for
    the OFA lookups, not a verified roster.
    """
    import re

    pattern = re.compile(
        r"\b(?:[A-Z][a-z'\-]{2,}\s){2,4}(?:[A-Z][a-z'\-]{2,})\b"
    )
    seen: dict[str, None] = {}
    for _, text in documents:
        for match in pattern.finditer(text or ""):
            phrase = " ".join(match.group(0).split())
            if 12 <= len(phrase) <= 60:
                seen.setdefault(phrase, None)
    return list(seen)[:40]
