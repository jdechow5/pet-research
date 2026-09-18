"""Data model. Every asserted fact carries where it came from and when.

The point of this tool is auditability: a breeder either is on the ALAA
Platinum list as of a timestamp, or the tool should say it does not know.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Retrieval(str, Enum):
    LIVE = "live"          # fetched over the network by this tool
    SAVED = "saved"        # parsed from HTML the user saved from a browser
    MANUAL = "manual"      # typed in by a human
    UNAVAILABLE = "unavailable"


class Registry(str, Enum):
    ALAA = "ALAA"
    WALA = "WALA"
    OFA = "OFA"
    BREEDER_SITE = "breeder_site"


class SizeVerdict(str, Enum):
    STANDARD_CONFIRMED = "standard_confirmed"
    STANDARD_LIKELY = "standard_likely"
    UNKNOWN = "unknown"
    STANDARD_UNLIKELY = "standard_unlikely"
    STANDARD_EXCLUDED = "standard_excluded"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


@dataclass
class Provenance:
    source: str
    url: str = ""
    retrieved_at: str = field(default_factory=utc_now)
    retrieval: Retrieval = Retrieval.LIVE
    note: str = ""


@dataclass
class Evidence:
    """A quotable reason for a claim. Quotes are verbatim page text."""
    claim: str
    quote: str = ""
    source_url: str = ""
    retrieved_at: str = field(default_factory=utc_now)

    def short(self, limit: int = 220) -> str:
        quote = " ".join(self.quote.split())
        return quote if len(quote) <= limit else quote[: limit - 1] + "…"


@dataclass
class BreederRecord:
    """One registry's listing for one kennel."""
    registry: Registry
    kennel: str
    registry_id: str = ""
    owner: str = ""
    city: str = ""
    region: str = ""            # 2-letter state/province code
    country: str = "US"
    website: str = ""
    domain: str = ""
    email: str = ""
    phone: str = ""
    awards: list[str] = field(default_factory=list)   # e.g. ["Platinum Paw"]
    detail_url: str = ""
    raw_text: str = ""
    provenance: Provenance | None = None

    @property
    def location(self) -> str:
        return ", ".join(p for p in (self.city, self.region) if p)


@dataclass
class MatchInfo:
    """How (and how confidently) two registry records were joined."""
    score: float = 0.0
    basis: list[str] = field(default_factory=list)
    status: str = "unmatched"   # matched | review | unmatched
    runners_up: list[str] = field(default_factory=list)


@dataclass
class SizeAssessment:
    verdict: SizeVerdict = SizeVerdict.UNKNOWN
    confidence: Confidence = Confidence.NONE
    sizes_seen: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)


@dataclass
class Signal:
    """A scoreable, evidence-backed attribute of a breeding program."""
    key: str
    label: str
    value: Any = None
    points: float = 0.0
    weight: float = 0.0
    evidence: list[Evidence] = field(default_factory=list)
    verified: bool = False


@dataclass
class Candidate:
    """A kennel as it survives (or fails) the protocol."""
    kennel: str
    alaa: BreederRecord | None = None
    wala: BreederRecord | None = None
    match: MatchInfo = field(default_factory=MatchInfo)
    size: SizeAssessment = field(default_factory=SizeAssessment)
    signals: list[Signal] = field(default_factory=list)
    score: float = 0.0
    stage_results: dict[str, bool] = field(default_factory=dict)
    exclusion_reasons: list[str] = field(default_factory=list)
    verification_links: dict[str, str] = field(default_factory=dict)
    followups: list[str] = field(default_factory=list)

    # -- derived views ---------------------------------------------------
    @property
    def region(self) -> str:
        for rec in (self.alaa, self.wala):
            if rec and rec.region:
                return rec.region
        return ""

    @property
    def city(self) -> str:
        for rec in (self.alaa, self.wala):
            if rec and rec.city:
                return rec.city
        return ""

    @property
    def website(self) -> str:
        for rec in (self.alaa, self.wala):
            if rec and rec.website:
                return rec.website
        return ""

    @property
    def domain(self) -> str:
        for rec in (self.alaa, self.wala):
            if rec and rec.domain:
                return rec.domain
        return ""

    @property
    def alaa_awards(self) -> list[str]:
        return list(self.alaa.awards) if self.alaa else []

    @property
    def wala_awards(self) -> list[str]:
        return list(self.wala.awards) if self.wala else []

    @property
    def passed(self) -> bool:
        return bool(self.stage_results) and all(self.stage_results.values())

    def signal(self, key: str) -> Signal | None:
        for sig in self.signals:
            if sig.key == key:
                return sig
        return None


def to_jsonable(obj: Any) -> Any:
    """Recursively convert dataclasses/enums into JSON-safe structures."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    return obj
