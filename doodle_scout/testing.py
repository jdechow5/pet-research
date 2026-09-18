"""A fixture-backed stand-in for HttpClient.

The fixtures contain invented kennels on reserved .example domains. No real
breeder, person or registry id appears in them, so a report generated from
them cannot be mistaken for a statement about an actual breeder.

Lets the whole protocol run end to end with no network, which is how the
joining, filtering, scoring and reporting logic is actually tested. It does
not, and cannot, prove that the live registry markup matches the fixtures.
"""

from __future__ import annotations

from pathlib import Path

from .http_client import FetchError, Response
from .models import utc_now

FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

ROUTES: list[tuple[str, str]] = [
    ("breedersearch", "alaa_listing.html"),
    ("all-star-breeders", "wala_allstar.html"),
    ("diamond-rewards-program", "wala_diamond.html"),
    ("quillfeather.example/about", "sites/quillfeather_about.html"),
    ("quillfeather.example/our-dogs", "sites/quillfeather_dogs.html"),
    ("quillfeather.example", "sites/quillfeather.html"),
    ("silvermarsh.example", "sites/silvermarsh.html"),
]


class FixtureClient:
    """Implements the surface of HttpClient that the sources use."""

    def __init__(self, fixtures_dir: Path | None = None, *, strict: bool = False):
        self.fixtures = Path(fixtures_dir or FIXTURES)
        self.strict = strict
        self.request_log: list[dict] = []

    def _resolve(self, url: str) -> Path | None:
        lowered = url.lower()
        for needle, filename in ROUTES:
            if needle in lowered:
                path = self.fixtures / filename
                if path.exists():
                    return path
        return None

    def get(self, url: str, *, use_cache: bool = True) -> Response:
        path = self._resolve(url)
        if path is None:
            self.request_log.append({"url": url, "method": "GET", "outcome": "no fixture"})
            raise FetchError(url, "no fixture registered for this URL")
        self.request_log.append({"url": url, "method": "GET", "outcome": "fixture"})
        return Response(
            url=url,
            status=200,
            text=path.read_text(encoding="utf-8"),
            retrieved_at=utc_now(),
        )

    def post(self, url: str, data: dict, *, use_cache: bool = True) -> Response:
        # The ALAA fixture is a single page, so a state postback returns it
        # unchanged. Dedupe downstream keeps that from inflating counts.
        return self.get(url)

    def first_reachable(self, urls: list[str]) -> Response:
        for url in urls:
            try:
                return self.get(url)
            except FetchError:
                continue
        raise FetchError(urls[0] if urls else "", "no fixture matched any mirror")
