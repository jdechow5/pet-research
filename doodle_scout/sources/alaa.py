"""Stage 1 of the protocol: the ALAA member breeder list.

ilainc.net is the ALAA's member-services host; breeders.alaa-labradoodles.com
serves the same application. The listing is regenerated every 24 hours, which
is why this is the authoritative list rather than any curated blog roundup.

Parsing strategy: anchor on links to BreederDetails.aspx, because that URL
shape (?id=NNNN&state=XX) is stable and gives us the record id and state for
free. Everything else is read out of the surrounding block. That survives
cosmetic redesigns far better than hardcoded control IDs or column indexes.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlsplit

from ..dom import Node, parse, squash
from ..http_client import FetchError, HttpClient, Response, load_saved_pages
from ..models import BreederRecord, Provenance, Registry, Retrieval
from ..normalize import US_STATES, region_code, registrable_domain
from ..webforms import (
    option_values,
    postback_links,
    postback_payload,
    form_action,
    select_matching_options,
)

DETAIL_HREF = re.compile(r"breederdetails\.aspx", re.I)
AWARD_WORDS = ("platinum", "gold", "silver", "bronze")
PHONE_RE = re.compile(r"(?:\+?1[\s.-]*)?\(?\b\d{3}\)?[\s.-]*\d{3}[\s.-]*\d{4}\b")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
CITY_STATE_RE = re.compile(r"([A-Za-z][A-Za-z .'\-]{1,40}),\s*([A-Z]{2})\b")
REGISTRY_HOSTS = ("ilainc.net", "alaa-labradoodles.com", "walalabradoodles.org")
NEXT_LABELS = ("next", ">", "»", "next page")


def detect_awards(block: Node, kennel: str) -> list[tuple[str, str]]:
    """Return [(award, basis)] found in a listing block.

    basis is one of:
      image        - read from a paw emblem's alt/title/src (most reliable)
      text_paw     - the word appeared next to "Paw"
      text_bare    - the word appeared alone; could be part of a kennel name

    The distinction matters. "Silver Marsh Labradoodles" contains the word
    "Silver" and holds no Silver Paw, so bare text hits are reported but
    never treated as authoritative.
    """
    found: dict[str, str] = {}

    def record(award: str, basis: str) -> None:
        rank = {"image": 3, "text_paw": 2, "text_bare": 1}
        if rank[basis] > rank.get(found.get(award, ""), 0):
            found[award] = basis

    for img in block.find_all("img"):
        haystack = " ".join(
            (img.get("alt"), img.get("title"), img.get("src"), img.get("class"))
        ).lower()
        for word in AWARD_WORDS:
            if word in haystack:
                record(word.capitalize(), "image")

    # Strip the kennel name out before reading text, so the name itself
    # cannot manufacture an award.
    text = block.text
    if kennel:
        text = text.replace(kennel, " ")
    lowered = text.lower()
    for word in AWARD_WORDS:
        for match in re.finditer(rf"\b{word}\b", lowered):
            window = lowered[match.start() : match.end() + 24]
            record(word.capitalize(), "text_paw" if "paw" in window else "text_bare")

    return sorted(found.items())


def _container_for(anchor: Node) -> Node:
    """The smallest sensible block describing one breeder."""
    for tag in ("tr", "li"):
        parent = anchor.find_parent(tag)
        if parent is not None:
            return parent
    node = anchor.parent
    best = anchor
    while node is not None and node.tag != "#document":
        if len(node.text) > 1200:
            break
        best = node
        node = node.parent
    return best


def _external_site(block: Node, base_url: str) -> str:
    for link in block.find_all("a"):
        href = link.get("href").strip()
        if not href.lower().startswith(("http://", "https://")):
            continue
        host = (urlsplit(href).hostname or "").lower()
        if any(host.endswith(reg) for reg in REGISTRY_HOSTS):
            continue
        return href
    return ""


def parse_listing(response: Response, base_url: str) -> list[BreederRecord]:
    """Extract every breeder record on one listing page."""
    doc = parse(response.text)
    records: list[BreederRecord] = []
    provenance = Provenance(
        source="ALAA member breeder search",
        url=response.url,
        retrieved_at=response.retrieved_at,
        retrieval=Retrieval.SAVED
        if response.url.startswith("file://")
        else Retrieval.LIVE,
    )

    for anchor in doc.find_all("a", attrs={"href": DETAIL_HREF}):
        href = anchor.get("href")
        query = parse_qs(urlsplit(href).query)
        block = _container_for(anchor)
        kennel = squash(anchor.text)
        if not kennel or len(kennel) < 2:
            continue

        block_text = block.block_text
        city, region = "", ""
        state_param = (query.get("state") or [""])[0].strip().upper()
        if state_param and len(state_param) == 2:
            region = state_param
        city_match = CITY_STATE_RE.search(block_text)
        if city_match:
            candidate_city = squash(city_match.group(1))
            candidate_region = city_match.group(2)
            if candidate_city.lower() != kennel.lower():
                city = candidate_city
            if not region:
                region = candidate_region
        if not region:
            region = region_code(block_text)

        email = ""
        for link in block.find_all("a", attrs={"href": re.compile(r"^mailto:", re.I)}):
            email = link.get("href")[7:].split("?")[0].strip()
            break
        if not email:
            found = EMAIL_RE.search(block_text)
            email = found.group(0) if found else ""

        phone_match = PHONE_RE.search(block_text)
        website = _external_site(block, base_url)

        awards = detect_awards(block, kennel)
        records.append(
            BreederRecord(
                registry=Registry.ALAA,
                kennel=kennel,
                registry_id=(query.get("id") or [""])[0],
                city=city,
                region=region,
                website=website,
                domain=registrable_domain(website),
                email=email,
                phone=phone_match.group(0) if phone_match else "",
                awards=[f"{name} ({basis})" for name, basis in awards],
                detail_url=urljoin(base_url, href),
                raw_text=block_text[:1000],
                provenance=provenance,
            )
        )
    return _dedupe(records)


def _dedupe(records: list[BreederRecord]) -> list[BreederRecord]:
    """Collapse duplicate rows, merging award evidence rather than dropping it."""
    by_key: dict[str, BreederRecord] = {}
    for record in records:
        key = record.registry_id or f"{record.kennel.lower()}|{record.region}"
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = record
            continue
        for award in record.awards:
            if award not in existing.awards:
                existing.awards.append(award)
        for attr in ("city", "region", "website", "domain", "email", "phone"):
            if not getattr(existing, attr) and getattr(record, attr):
                setattr(existing, attr, getattr(record, attr))
    return list(by_key.values())


def collect(
    client: HttpClient,
    config,
    saved_dir=None,
    *,
    regions: list[str] | None = None,
    max_pages_per_region: int = 25,
) -> tuple[list[BreederRecord], list[str]]:
    """Gather the national ALAA list. Returns (records, notes).

    Notes are human-readable warnings meant for the report's provenance
    section, so a thin result set is never mistaken for a clean one.
    """
    notes: list[str] = []

    saved = load_saved_pages(saved_dir) if saved_dir else []
    if saved:
        records: list[BreederRecord] = []
        for response in saved:
            records.extend(parse_listing(response, "https://ilainc.net"))
        notes.append(
            f"ALAA: parsed {len(saved)} saved page(s) from {saved_dir}; "
            "no live request was made."
        )
        return _dedupe(records), notes

    bases = config.get("sources.alaa_base_urls", [])
    search_path = config.get("sources.alaa_search_path", "/guest/breedersearch.aspx")
    urls = [base.rstrip("/") + search_path for base in bases]

    try:
        first = client.first_reachable(urls)
    except FetchError as exc:
        notes.append(f"ALAA: UNREACHABLE. {exc.reason}")
        return [], notes

    base_url = f"{urlsplit(first.url).scheme}://{urlsplit(first.url).netloc}"
    records = parse_listing(first, base_url)
    notes.append(f"ALAA: landing page {first.url} yielded {len(records)} record(s).")

    doc = parse(first.text)
    state_select = select_matching_options(doc, set(US_STATES.values()) | set(US_STATES))
    wanted = [r.upper() for r in (regions or [])]

    if state_select is None:
        notes.append(
            "ALAA: no state dropdown found; relying on the default listing and "
            "its pager only. If the result count looks low, save the page from "
            "your browser into data/raw/alaa/ and re-run with --from-saved."
        )
        records.extend(
            _follow_pager(client, doc, first, base_url, max_pages_per_region, notes)
        )
        return _dedupe(records), notes

    options = option_values(state_select)
    if wanted:
        options = [(v, l) for v, l in options if region_code(v) in wanted or region_code(l) in wanted]
    notes.append(f"ALAA: iterating {len(options)} region option(s) from the search form.")

    action = urljoin(first.url, form_action(doc, first.url))
    for value, label in options:
        payload = postback_payload(
            doc, target="", argument="", overrides={state_select.get("name"): value}
        )
        try:
            response = client.post(action, payload)
        except FetchError as exc:
            notes.append(f"ALAA: region {label} failed ({exc.reason}).")
            continue
        page_records = parse_listing(response, base_url)
        records.extend(page_records)
        page_doc = parse(response.text)
        records.extend(
            _follow_pager(
                client, page_doc, response, base_url, max_pages_per_region, notes
            )
        )

    return _dedupe(records), notes


def _follow_pager(
    client: HttpClient,
    doc: Node,
    response: Response,
    base_url: str,
    max_pages: int,
    notes: list[str],
) -> list[BreederRecord]:
    """Walk 'Next' postback links until they run out."""
    collected: list[BreederRecord] = []
    current_doc, current = doc, response
    for _ in range(max_pages):
        target = None
        for label, control, argument in postback_links(current_doc):
            if squash(label).lower() in NEXT_LABELS:
                target = (control, argument)
                break
        if target is None:
            break
        action = urljoin(current.url, form_action(current_doc, current.url))
        payload = postback_payload(current_doc, target[0], target[1])
        try:
            current = client.post(action, payload)
        except FetchError as exc:
            notes.append(f"ALAA: pagination stopped ({exc.reason}).")
            break
        current_doc = parse(current.text)
        page = parse_listing(current, base_url)
        if not page:
            break
        collected.extend(page)
    return collected
