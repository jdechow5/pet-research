"""Read a breeder's own site for what the registries do not carry.

ALAA Platinum and WALA Diamond both certify testing paperwork. Neither
says anything about how puppies are raised, which is what actually drives
whether a dog turns out well adjusted. Those signals only exist in prose on
the breeder's own site, so they are collected here with the sentence that
justifies them, and the human still gets to read the quote.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

from ..dom import parse
from ..http_client import FetchError, HttpClient
from ..models import Evidence

# Pages worth reading, in rough order of usefulness.
PAGE_HINTS = (
    "about", "our-dogs", "ourdogs", "dogs", "size", "sizes", "puppies",
    "puppy", "health", "testing", "program", "raising", "philosophy",
    "guardian", "available", "litters", "contract", "faq", "girls", "boys",
    "parents", "breeding", "adults", "process", "nursery",
)

SIGNAL_PATTERNS: dict[str, tuple[str, tuple[str, ...]]] = {
    "raised_in_home": (
        "Puppies raised inside the home",
        (
            r"raised\s+(?:in|inside)\s+(?:our|the|my)\s+home",
            r"\bin[-\s]home\s+(?:raised|program|breeding)",
            r"\bunderfoot\b",
            r"\bnot\s+kenneled\b",
            r"\bin\s+our\s+(?:living\s+room|kitchen|family\s+room)",
            r"\bguardian\s+home",
        ),
    ),
    "early_development_curriculum": (
        "Named early-development curriculum",
        (
            r"\bpuppy\s+culture\b",
            r"\bavidog\b",
            r"\bearly\s+neuro(?:logical)?\s+stimulation\b",
            r"\b(?:ens|esi)\b(?=[^a-z])",
            r"\bearly\s+scent\s+introduction\b",
            r"\bbio[-\s]?sensor\b",
            r"\bempowered\s+puppy\b",
            r"\bsound\s+(?:conditioning|desensitiz)",
            r"\bsocialization\s+(?:protocol|program|curriculum|checklist)",
            r"\bbadass\s+breeder\b",
        ),
    ),
    "temperament_testing": (
        "Formal temperament or aptitude testing",
        (
            r"\bvolhard\b",
            r"\bpuppy\s+aptitude\s+test",
            r"\btemperament\s+(?:test|testing|assessment|evaluat)",
            r"\bakc\s+temperament\b",
            r"\bbehaviou?ral\s+assessment\b",
        ),
    ),
    "breeding_dog_transparency": (
        "Health results published per breeding dog",
        (
            r"\bofa\b",
            r"\bpennhip\b",
            r"\bcaer\b|\bcerf\b",
            r"\bcardiac\s+(?:clearance|exam|evaluation)",
            r"\bembark\b",
            r"\bpaw\s+print\s+genetics\b",
            r"\bgenetic\s+panel\b",
            r"\bdna\s+(?:panel|profile|test)",
        ),
    ),
    "health_guarantee": (
        "Written health guarantee",
        (
            r"\bhealth\s+(?:guarantee|warranty)",
            r"\b(?:two|2|three|3)[-\s]year\s+(?:health\s+)?(?:guarantee|warranty)",
            r"\bpurchase\s+agreement\b",
        ),
    ),
    "litter_cadence_disclosed": (
        "Litter frequency stated",
        (
            r"\b(?:one|two|three|four|1|2|3|4)\s+litters?\s+(?:per|a)\s+year",
            r"\blitters?\s+(?:per|a)\s+year\b",
            r"\b(?:we|i)\s+(?:only\s+)?(?:have|raise|breed)\s+\w+\s+litters?\s+(?:per|a)\s+year",
        ),
    ),
}


def _relevant_links(doc, page_url: str, limit: int) -> list[str]:
    host = urlsplit(page_url).netloc.lower()
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()
    for link in doc.find_all("a"):
        href = link.get("href").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(page_url, href).split("#")[0]
        if urlsplit(absolute).netloc.lower() != host:
            continue
        if absolute in seen or absolute.rstrip("/") == page_url.rstrip("/"):
            continue
        blob = (absolute + " " + link.text).lower()
        hits = sum(1 for hint in PAGE_HINTS if hint in blob)
        if hits:
            seen.add(absolute)
            scored.append((hits, absolute))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [url for _, url in scored[:limit]]


def read_site(
    client: HttpClient, website: str, *, max_pages: int = 7
) -> tuple[list[tuple[str, str]], list[str]]:
    """Fetch a breeder site. Returns ([(url, text), ...], notes)."""
    notes: list[str] = []
    if not website:
        return [], ["no website listed in either registry"]

    documents: list[tuple[str, str]] = []
    try:
        home = client.get(website)
    except FetchError as exc:
        return [], [f"site unreachable: {exc.reason}"]

    doc = parse(home.text)
    documents.append((home.url, doc.block_text))
    for url in _relevant_links(doc, home.url, max_pages - 1):
        try:
            page = client.get(url)
        except FetchError as exc:
            notes.append(f"{url}: {exc.reason}")
            continue
        documents.append((page.url, parse(page.text).block_text))

    notes.append(f"read {len(documents)} page(s) from {urlsplit(home.url).netloc}")
    return documents, notes


def detect_signals(
    documents: list[tuple[str, str]]
) -> dict[str, list[Evidence]]:
    """Find program signals with the sentence that supports each one."""
    found: dict[str, list[Evidence]] = {}
    for key, (label, patterns) in SIGNAL_PATTERNS.items():
        for url, text in documents:
            flat = " ".join((text or "").split())
            for pattern in patterns:
                match = re.search(pattern, flat, re.I)
                if not match:
                    continue
                lo = max(0, match.start() - 110)
                hi = min(len(flat), match.end() + 110)
                found.setdefault(key, []).append(
                    Evidence(
                        claim=label,
                        quote=flat[lo:hi].strip(),
                        source_url=url,
                    )
                )
                break
            if key in found and len(found[key]) >= 2:
                break
    return found


def adult_photo_pages(documents: list[tuple[str, str]]) -> list[str]:
    """Pages most likely to show adult dogs.

    Coat, structure and expression are the things you have to judge with
    your own eyes, and puppy photos tell you almost nothing about them.
    """
    wanted = ("our-dogs", "ourdogs", "girls", "boys", "dams", "sires",
              "parents", "adults", "our-family", "breeding")
    return [url for url, _ in documents if any(w in url.lower() for w in wanted)]
