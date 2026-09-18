"""Stage 2 of the protocol: WALA ratings.

Important correction encoded here. WALA's Star Rewards Program, which is
where the "All Star" title came from, was restructured into the Diamond
Rewards Program (One / Two / Three Diamonds). WALA moved the old program
to a page literally pathed /old-star-program, and Star badges stopped
being valid on member websites after April 2026. So a current search
should key on Diamond level, and treat "All Star" as a legacy signal that
a breeder cleared a high bar at some point before the changeover.

Parsing strategy: WALA publishes a member id in the form WALA-0619-00755.
That pattern is a reliable record delimiter regardless of whether the page
is laid out as a table or as stacked Wix text blocks.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

from ..dom import Node, parse, squash
from ..http_client import FetchError, HttpClient, Response, load_saved_pages
from ..models import BreederRecord, Provenance, Registry, Retrieval
from ..normalize import region_code, registrable_domain

WALA_ID = re.compile(r"\bWALA[-\s]?(\d{3,4})[-\s]?(\d{4,6})\b", re.I)
DIAMOND_LEVEL = re.compile(
    r"\b(one|two|three|1|2|3)[\s-]*diamond", re.I
)
ALL_STAR = re.compile(r"\ball[\s-]?stars?\b", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+?1[\s.-]*)?\(?\b\d{3}\)?[\s.-]*\d{3}[\s.-]*\d{4}\b")
CITY_REGION = re.compile(r"([A-Za-z][A-Za-z .'\-]{1,40}),\s*([A-Z]{2})\b")
RATING_PAGE_HINT = re.compile(r"diamond|all[-\s]?star|star[-\s]?reward", re.I)
LEVEL_WORDS = {"one": "One Diamond", "1": "One Diamond",
               "two": "Two Diamond", "2": "Two Diamond",
               "three": "Three Diamond", "3": "Three Diamond"}

SKIP_HOSTS = ("walalabradoodles.org", "wixstatic.com", "wix.com",
              "facebook.com", "instagram.com", "youtube.com", "google.com")


def normalize_rating(text: str) -> str:
    """Pull a rating label out of arbitrary page text."""
    diamond = DIAMOND_LEVEL.search(text or "")
    if diamond:
        return LEVEL_WORDS.get(diamond.group(1).lower(), "Diamond")
    if ALL_STAR.search(text or ""):
        return "All Star"
    return ""


def _site_from(block: Node) -> str:
    for link in block.find_all("a"):
        href = link.get("href").strip()
        if not href.lower().startswith(("http://", "https://")):
            continue
        host = (urlsplit(href).hostname or "").lower()
        if any(host.endswith(skip) for skip in SKIP_HOSTS):
            continue
        return href
    return ""


def _record_from_text(
    chunk: str, wala_id: str, rating: str, provenance: Provenance, website: str = ""
) -> BreederRecord | None:
    """Build a record from one text chunk delimited by a WALA id."""
    lines = [squash(line) for line in chunk.splitlines()]
    lines = [line for line in lines if line and not WALA_ID.fullmatch(line)]
    lines = [WALA_ID.sub("", line).strip(" ,|-") for line in lines]
    lines = [line for line in lines if line]
    if not lines:
        return None

    city, region = "", ""
    location_line = ""
    for line in lines:
        match = CITY_REGION.search(line)
        if match:
            city, region = squash(match.group(1)), match.group(2)
            location_line = line
            break
    if not region:
        for line in lines:
            code = region_code(line)
            if code:
                region = code
                location_line = line
                break

    email = ""
    phone = ""
    for line in lines:
        if not email:
            found = EMAIL_RE.search(line)
            email = found.group(0) if found else ""
        if not phone:
            found = PHONE_RE.search(line)
            phone = found.group(0) if found else ""

    # The kennel name is the first line that is not the location, an
    # email, a phone number or a bare country.
    kennel = ""
    for line in lines:
        if line == location_line or EMAIL_RE.search(line) or PHONE_RE.fullmatch(line):
            continue
        if line.lower() in ("united states", "usa", "canada", "australia"):
            continue
        if len(line) < 3:
            continue
        kennel = line
        break
    if not kennel:
        kennel = lines[0]

    owner = ""
    for line in lines:
        if line in (kennel, location_line):
            continue
        if re.fullmatch(r"[A-Z][a-z'\-]+(?:\s+[A-Z][a-z'\-.]+){1,2}", line):
            owner = line
            break

    country = "US"
    if re.search(r"\bcanada\b", chunk, re.I):
        country = "CA"
    elif re.search(r"\baustralia\b", chunk, re.I):
        country = "AU"

    return BreederRecord(
        registry=Registry.WALA,
        kennel=kennel,
        registry_id=wala_id,
        owner=owner,
        city=city,
        region=region,
        country=country,
        website=website,
        domain=registrable_domain(website),
        email=email,
        phone=phone,
        awards=[rating] if rating else [],
        detail_url=provenance.url,
        raw_text=chunk[:1000],
        provenance=provenance,
    )


def parse_breeder_page(
    response: Response, declared_rating: str = ""
) -> list[BreederRecord]:
    """Extract records from a WALA listing page.

    Tries a row-based read first (one WALA id per table row or repeated
    block), then falls back to splitting the page text on WALA ids.
    """
    doc = parse(response.text)
    provenance = Provenance(
        source="WALA",
        url=response.url,
        retrieved_at=response.retrieved_at,
        retrieval=Retrieval.SAVED
        if response.url.startswith("file://")
        else Retrieval.LIVE,
    )
    page_rating = declared_rating or normalize_rating(doc.text)
    records: list[BreederRecord] = []

    blocks: list[Node] = []
    for node in doc.find_all(("tr", "li", "article", "section", "div")):
        text = node.text
        ids = WALA_ID.findall(text)
        if len(ids) == 1 and len(text) < 1500:
            # Prefer the innermost block holding exactly one id.
            if not any(node is child for b in blocks for child in b.walk()):
                blocks.append(node)

    seen_ids: set[str] = set()
    for block in blocks:
        match = WALA_ID.search(block.text)
        if not match:
            continue
        wala_id = f"WALA-{match.group(1)}-{match.group(2)}"
        if wala_id in seen_ids:
            continue
        rating = normalize_rating(block.text) or page_rating
        record = _record_from_text(
            block.block_text, wala_id, rating, provenance, _site_from(block)
        )
        if record and record.kennel:
            seen_ids.add(wala_id)
            records.append(record)

    if not records:
        page_text = doc.block_text
        positions = [(m.start(), m) for m in WALA_ID.finditer(page_text)]
        for index, (start, match) in enumerate(positions):
            end = positions[index + 1][0] if index + 1 < len(positions) else len(page_text)
            chunk = page_text[max(0, start - 200) : end]
            wala_id = f"WALA-{match.group(1)}-{match.group(2)}"
            if wala_id in seen_ids:
                continue
            rating = normalize_rating(chunk) or page_rating
            record = _record_from_text(chunk, wala_id, rating, provenance)
            if record and record.kennel:
                seen_ids.add(wala_id)
                records.append(record)

    return records


def collect(
    client: HttpClient, config, saved_dir=None
) -> tuple[list[BreederRecord], list[str]]:
    """Gather WALA records across the rating pages. Returns (records, notes)."""
    notes: list[str] = []

    saved = load_saved_pages(saved_dir) if saved_dir else []
    if saved:
        records: list[BreederRecord] = []
        for response in saved:
            declared = ""
            name = response.url.lower()
            if "all" in name and "star" in name:
                declared = "All Star"
            elif "diamond" in name:
                declared = ""
            records.extend(parse_breeder_page(response, declared))
        notes.append(
            f"WALA: parsed {len(saved)} saved page(s) from {saved_dir}; "
            "no live request was made."
        )
        return _merge(records), notes

    base = config.get("sources.wala_base_url", "").rstrip("/")
    pages = config.get("sources.wala_pages", [])
    records = []
    visited: set[str] = set()

    for entry in pages:
        url = urljoin(base + "/", entry.get("path", "").lstrip("/"))
        if url in visited:
            continue
        visited.add(url)
        try:
            response = client.get(url)
        except FetchError as exc:
            notes.append(f"WALA: {url} unreachable ({exc.reason}).")
            continue
        found = parse_breeder_page(response, entry.get("rating", ""))
        notes.append(
            f"WALA: {url} -> {len(found)} record(s)"
            + (f" [{entry.get('rating')}]" if entry.get("rating") else "")
            + "."
        )
        records.extend(found)

        if entry.get("kind") == "rating" and config.get(
            "sources.wala_discover_rating_pages", True
        ):
            for link_url in _rating_subpages(response, base):
                if link_url in visited:
                    continue
                visited.add(link_url)
                try:
                    sub = client.get(link_url)
                except FetchError as exc:
                    notes.append(f"WALA: {link_url} unreachable ({exc.reason}).")
                    continue
                sub_found = parse_breeder_page(sub)
                notes.append(f"WALA: {link_url} -> {len(sub_found)} record(s).")
                records.extend(sub_found)

    if not records:
        notes.append(
            "WALA: no records parsed. The rating pages may be rendered by "
            "client-side script, in which case open them in your browser, "
            "save as HTML into data/raw/wala/, and re-run with --from-saved."
        )
    return _merge(records), notes


def _rating_subpages(response: Response, base: str) -> list[str]:
    """Follow links that look like per-level Diamond pages."""
    doc = parse(response.text)
    out = []
    host = urlsplit(base).netloc
    for link in doc.find_all("a"):
        href = link.get("href").strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        absolute = urljoin(response.url, href)
        if urlsplit(absolute).netloc != host:
            continue
        if RATING_PAGE_HINT.search(absolute) or RATING_PAGE_HINT.search(link.text):
            if "old-star-program" in absolute.lower():
                continue
            out.append(absolute.split("#")[0])
    return sorted(set(out))


def _merge(records: list[BreederRecord]) -> list[BreederRecord]:
    """One record per WALA id, keeping the strongest rating seen."""
    rank = {"Three Diamond": 4, "Two Diamond": 3, "One Diamond": 2,
            "Diamond": 1, "All Star": 1}
    by_id: dict[str, BreederRecord] = {}
    for record in records:
        key = record.registry_id or record.kennel.lower()
        existing = by_id.get(key)
        if existing is None:
            by_id[key] = record
            continue
        for award in record.awards:
            if award and award not in existing.awards:
                existing.awards.append(award)
        existing.awards.sort(key=lambda a: -rank.get(a, 0))
        for attr in ("owner", "city", "region", "website", "domain", "email", "phone"):
            if not getattr(existing, attr) and getattr(record, attr):
                setattr(existing, attr, getattr(record, attr))
    return list(by_id.values())
