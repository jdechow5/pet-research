"""Transparent scoring over verifiable signals only.

Deliberately absent: any score for appearance. Coat, structure and
expression cannot be read off a registry listing or a marketing page, and a
number invented for them would look like evidence while carrying none. The
report collects adult-dog photo pages instead, so that judgement stays with
the person making it.

Every weight lives in config/search.json. Every point is attributable to a
named signal, so a ranking can always be explained.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from .models import Candidate, Confidence, Evidence, Signal, SizeVerdict

HOME_COORDS = {"Portland,OR": (45.5152, -122.6784)}

# Population-weighted-ish state centroids. Good enough to band travel;
# not a substitute for a real address once you have one.
STATE_CENTROIDS = {
    "AL": (32.8, -86.8), "AK": (64.0, -152.0), "AZ": (34.3, -111.7),
    "AR": (34.9, -92.4), "CA": (37.2, -119.5), "CO": (39.0, -105.5),
    "CT": (41.6, -72.7), "DE": (39.0, -75.5), "DC": (38.9, -77.0),
    "FL": (28.6, -82.4), "GA": (32.6, -83.4), "HI": (20.8, -156.3),
    "ID": (44.4, -114.6), "IL": (40.0, -89.2), "IN": (39.9, -86.3),
    "IA": (42.1, -93.5), "KS": (38.5, -98.4), "KY": (37.5, -85.3),
    "LA": (31.1, -92.0), "ME": (45.4, -69.2), "MD": (39.0, -76.8),
    "MA": (42.3, -71.8), "MI": (44.3, -85.4), "MN": (46.3, -94.3),
    "MS": (32.7, -89.7), "MO": (38.4, -92.5), "MT": (47.0, -109.6),
    "NE": (41.5, -99.8), "NV": (39.3, -116.6), "NH": (43.7, -71.6),
    "NJ": (40.2, -74.7), "NM": (34.4, -106.1), "NY": (42.9, -75.5),
    "NC": (35.5, -79.4), "ND": (47.4, -100.5), "OH": (40.3, -82.8),
    "OK": (35.6, -97.5), "OR": (43.9, -120.6), "PA": (40.9, -77.8),
    "RI": (41.7, -71.6), "SC": (33.9, -80.9), "SD": (44.4, -100.2),
    "TN": (35.8, -86.4), "TX": (31.5, -99.3), "UT": (39.3, -111.7),
    "VT": (44.1, -72.7), "VA": (37.5, -78.9), "WA": (47.4, -120.4),
    "WV": (38.6, -80.6), "WI": (44.6, -89.7), "WY": (43.0, -107.6),
    "BC": (53.7, -125.0), "AB": (54.0, -115.0), "ON": (50.0, -85.0),
    "QC": (52.0, -72.0), "MB": (54.0, -97.0), "SK": (54.0, -106.0),
    "NS": (45.0, -63.0), "NB": (46.5, -66.0), "PE": (46.4, -63.2),
    "NL": (53.1, -57.6),
}

TRAVEL_BANDS = (
    (350, "same-day drive", 1.0),
    (800, "long drive or short hop", 0.7),
    (1800, "flight, one-day trip possible", 0.4),
    (float("inf"), "long flight", 0.2),
)

WALA_POINTS = {
    "Three Diamond": 1.0,
    "Two Diamond": 0.8,
    "One Diamond": 0.6,
    "Diamond": 0.6,
    "All Star": 0.5,  # legacy program, retired; see docs/PROTOCOL.md
}

SIZE_POINTS = {
    SizeVerdict.STANDARD_CONFIRMED: 1.0,
    SizeVerdict.STANDARD_LIKELY: 0.7,
    SizeVerdict.UNKNOWN: 0.3,
    SizeVerdict.STANDARD_UNLIKELY: 0.1,
    SizeVerdict.STANDARD_EXCLUDED: 0.0,
}


def great_circle_miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (a[0], a[1], b[0], b[1]))
    d_lat, d_lon = lat2 - lat1, lon2 - lon1
    h = sin(d_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(d_lon / 2) ** 2
    return 2 * 3958.8 * asin(sqrt(h))


def travel_estimate(region: str, home: tuple[float, float]) -> tuple[float, str, float]:
    """(miles, band label, points). Miles is -1 when the state is unknown."""
    coords = STATE_CENTROIDS.get((region or "").upper())
    if not coords:
        return -1.0, "unknown location", 0.0
    miles = great_circle_miles(home, coords)
    for limit, label, points in TRAVEL_BANDS:
        if miles <= limit:
            return round(miles), label, points
    return round(miles), "long flight", 0.2


def _platinum_points(candidate: Candidate) -> tuple[float, str]:
    for award in candidate.alaa_awards:
        if award.lower().startswith("platinum"):
            if "(image)" in award or "(text_paw)" in award:
                return 1.0, award
            return 0.5, award + " - weak evidence, confirm on the listing"
    return 0.0, "no Platinum Paw found"


def _wala_points(candidate: Candidate) -> tuple[float, str]:
    best, label = 0.0, "no WALA rating found"
    for award in candidate.wala_awards:
        points = WALA_POINTS.get(award, 0.0)
        if points > best:
            best, label = points, award
    if label == "All Star":
        label = "All Star (legacy Star Rewards Program, retired)"
    return best, label


def score_candidate(
    candidate: Candidate,
    config,
    site_signals: dict[str, list[Evidence]] | None = None,
    manual: dict | None = None,
) -> Candidate:
    weights = config.get("scoring.weights", {}) or {}
    home_key = (
        f"{config.get('home.city', 'Portland')},{config.get('home.region', 'OR')}"
    )
    home = HOME_COORDS.get(home_key, HOME_COORDS["Portland,OR"])
    site_signals = site_signals or {}
    manual = manual or {}

    signals: list[Signal] = []

    def add(key: str, label: str, points: float, value, evidence=None, verified=False):
        weight = float(weights.get(key, 0.0))
        signals.append(
            Signal(
                key=key,
                label=label,
                value=value,
                points=round(points, 3),
                weight=weight,
                evidence=evidence or [],
                verified=verified,
            )
        )

    points, label = _platinum_points(candidate)
    add("alaa_platinum", "ALAA Platinum Paw", points, label)

    points, label = _wala_points(candidate)
    add("wala_diamond", "WALA rating", points, label)

    dual = 1.0 if candidate.match.status == "matched" else (
        0.5 if candidate.match.status == "review" else 0.0
    )
    add(
        "dual_accountability",
        "Accountable to both rule sets",
        dual,
        candidate.match.status,
    )

    ofa = manual.get("ofa_verified")
    add(
        "ofa_verified",
        "Hip/elbow clearances confirmed in OFA",
        1.0 if ofa is True else 0.0,
        "confirmed by you" if ofa is True else "not yet checked",
        verified=ofa is True,
    )

    add(
        "standard_size",
        "Standard-size program",
        SIZE_POINTS.get(candidate.size.verdict, 0.0),
        candidate.size.verdict.value,
        candidate.size.evidence[:3],
    )

    for key, label in (
        ("raised_in_home", "Raised in the home"),
        ("early_development_curriculum", "Named early-development curriculum"),
        ("temperament_testing", "Temperament or aptitude testing"),
        ("breeding_dog_transparency", "Per-dog health results published"),
        ("health_guarantee", "Written health guarantee"),
        ("litter_cadence_disclosed", "Litter frequency disclosed"),
    ):
        evidence = site_signals.get(key, [])
        add(key, label, 1.0 if evidence else 0.0,
            "found" if evidence else "not found on site", evidence[:2])

    miles, band, travel_points = travel_estimate(candidate.region, home)
    add(
        "travel_band",
        "Reachable for an in-person visit",
        travel_points,
        f"{band}" + (f", about {int(miles):,} mi" if miles >= 0 else ""),
    )

    earned = sum(s.points * s.weight for s in signals)
    possible = sum(s.weight for s in signals) or 1.0
    candidate.signals = signals
    candidate.score = round(100 * earned / possible, 1)
    return candidate
