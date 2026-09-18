"""A deliberately polite, cache-first HTTP client built on stdlib only.

Design notes:
  * Cookies are kept, because the ALAA member search is ASP.NET WebForms
    and paging depends on session state.
  * Everything is cached on disk, so re-running the protocol does not
    re-hammer either registry. The ALAA list only changes every 24h.
  * robots.txt is honored by default.
  * Failure is loud and specific, so the CLI can suggest the saved-HTML
    path instead of silently producing an empty result.
"""

from __future__ import annotations

import gzip
import hashlib
import http.cookiejar
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
import zlib
from dataclasses import dataclass
from pathlib import Path

from .models import Provenance, Retrieval, utc_now


class FetchError(RuntimeError):
    """Raised when a URL could not be retrieved after retries."""

    def __init__(self, url: str, reason: str):
        self.url = url
        self.reason = reason
        super().__init__(f"{url}: {reason}")


class RobotsDisallowed(FetchError):
    pass


@dataclass
class Response:
    url: str
    status: int
    text: str
    from_cache: bool = False
    retrieved_at: str = ""

    def provenance(self, source: str, note: str = "") -> Provenance:
        return Provenance(
            source=source,
            url=self.url,
            retrieved_at=self.retrieved_at or utc_now(),
            retrieval=Retrieval.LIVE,
            note=note or ("served from local cache" if self.from_cache else ""),
        )


class HttpClient:
    def __init__(
        self,
        *,
        user_agent: str,
        cache_dir: Path,
        min_interval: float = 2.0,
        timeout: int = 30,
        max_retries: int = 3,
        cache_ttl_hours: float = 12.0,
        respect_robots: bool = True,
        offline: bool = False,
    ):
        self.user_agent = user_agent
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.min_interval = min_interval
        self.timeout = timeout
        self.max_retries = max_retries
        self.cache_ttl = cache_ttl_hours * 3600
        self.respect_robots = respect_robots
        self.offline = offline

        self.cookies = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies),
            _NoRedirectLoop(),
        )
        self._last_request_at = 0.0
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.request_log: list[dict] = []

    # -- public API ------------------------------------------------------
    def get(self, url: str, *, use_cache: bool = True) -> Response:
        return self._request("GET", url, None, use_cache=use_cache)

    def post(
        self, url: str, data: dict[str, str], *, use_cache: bool = True
    ) -> Response:
        body = urllib.parse.urlencode(data, doseq=True).encode()
        return self._request("POST", url, body, use_cache=use_cache)

    def first_reachable(self, urls: list[str]) -> Response:
        """Try mirrors in order. ALAA serves the same app on two hostnames."""
        problems = []
        for url in urls:
            try:
                return self.get(url)
            except FetchError as exc:
                problems.append(f"  {url}\n    -> {exc.reason}")
        raise FetchError(
            urls[0] if urls else "(no urls)",
            "no mirror was reachable:\n" + "\n".join(problems),
        )

    # -- internals -------------------------------------------------------
    def _request(
        self, method: str, url: str, body: bytes | None, *, use_cache: bool
    ) -> Response:
        key = self._cache_key(method, url, body)
        if use_cache:
            cached = self._read_cache(key)
            if cached is not None:
                self.request_log.append(
                    {"url": url, "method": method, "outcome": "cache"}
                )
                return cached

        if self.offline:
            raise FetchError(url, "offline mode is on and nothing is cached for this URL")

        if self.respect_robots and not self._robots_allow(url):
            raise RobotsDisallowed(url, "robots.txt disallows this path for our user agent")

        last_reason = "unknown error"
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            request = urllib.request.Request(url, data=body, method=method)
            request.add_header("User-Agent", self.user_agent)
            request.add_header("Accept", "text/html,application/xhtml+xml,*/*;q=0.8")
            request.add_header("Accept-Language", "en-US,en;q=0.9")
            request.add_header("Accept-Encoding", "gzip, deflate")
            if body is not None:
                request.add_header(
                    "Content-Type", "application/x-www-form-urlencoded"
                )
            try:
                with self._opener.open(request, timeout=self.timeout) as raw:
                    payload = _decode(raw.read(), raw.headers)
                    response = Response(
                        url=raw.geturl(),
                        status=getattr(raw, "status", 200) or 200,
                        text=payload,
                        retrieved_at=utc_now(),
                    )
                self._write_cache(key, response)
                self.request_log.append(
                    {"url": url, "method": method, "outcome": f"{response.status}"}
                )
                return response
            except urllib.error.HTTPError as exc:
                last_reason = f"HTTP {exc.code} {exc.reason}"
                # Client errors other than rate limiting will not fix
                # themselves on a retry.
                if exc.code not in (408, 425, 429, 500, 502, 503, 504):
                    break
            except urllib.error.URLError as exc:
                last_reason = f"network error: {exc.reason}"
            except TimeoutError:
                last_reason = f"timed out after {self.timeout}s"
            except Exception as exc:  # pragma: no cover - defensive
                last_reason = f"{type(exc).__name__}: {exc}"
            if attempt < self.max_retries:
                time.sleep(min(2 ** attempt, 16))

        self.request_log.append(
            {"url": url, "method": method, "outcome": f"failed: {last_reason}"}
        )
        raise FetchError(url, last_reason)

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request_at = time.monotonic()

    def _robots_allow(self, url: str) -> bool:
        parts = urllib.parse.urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            parser = urllib.robotparser.RobotFileParser()
            parser.set_url(origin + "/robots.txt")
            try:
                self._throttle()
                request = urllib.request.Request(
                    origin + "/robots.txt",
                    headers={"User-Agent": self.user_agent},
                )
                with self._opener.open(request, timeout=self.timeout) as raw:
                    parser.parse(_decode(raw.read(), raw.headers).splitlines())
                self._robots[origin] = parser
            except Exception:
                # No robots.txt, or it could not be read. Absence is not a
                # prohibition, but record that we could not check.
                self._robots[origin] = None
        parser = self._robots[origin]
        if parser is None:
            return True
        return parser.can_fetch(self.user_agent, url)

    def _cache_key(self, method: str, url: str, body: bytes | None) -> str:
        digest = hashlib.sha256()
        digest.update(method.encode())
        digest.update(b"\x00")
        digest.update(url.encode())
        if body:
            digest.update(b"\x00")
            digest.update(body)
        return digest.hexdigest()[:40]

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _read_cache(self, key: str) -> Response | None:
        path = self._cache_path(key)
        if not path.exists():
            return None
        try:
            blob = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        age = time.time() - path.stat().st_mtime
        if self.cache_ttl >= 0 and age > self.cache_ttl:
            return None
        return Response(
            url=blob.get("url", ""),
            status=blob.get("status", 200),
            text=blob.get("text", ""),
            from_cache=True,
            retrieved_at=blob.get("retrieved_at", ""),
        )

    def _write_cache(self, key: str, response: Response) -> None:
        try:
            self._cache_path(key).write_text(
                json.dumps(
                    {
                        "url": response.url,
                        "status": response.status,
                        "text": response.text,
                        "retrieved_at": response.retrieved_at,
                    }
                )
            )
        except OSError:
            pass  # a warm cache is a nicety, not a requirement


class _NoRedirectLoop(urllib.request.HTTPRedirectHandler):
    """Cap redirects so a misconfigured site cannot spin us forever."""

    max_redirections = 6


def _decode(raw: bytes, headers) -> str:
    encoding = (headers.get("Content-Encoding") or "").lower()
    if "gzip" in encoding:
        try:
            raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
        except OSError:
            pass
    elif "deflate" in encoding:
        try:
            raw = zlib.decompress(raw, -zlib.MAX_WBITS)
        except zlib.error:
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                pass
    charset = ""
    content_type = headers.get("Content-Type") or ""
    if "charset=" in content_type.lower():
        charset = content_type.lower().split("charset=")[-1].split(";")[0].strip()
    for candidate in (charset, "utf-8", "cp1252"):
        if not candidate:
            continue
        try:
            return raw.decode(candidate)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def load_saved_pages(directory: Path, pattern: str = "*.htm*") -> list[Response]:
    """Read HTML the user saved from a browser.

    This is the path that always works: if a registry blocks automated
    requests, saving the page by hand still feeds the same parsers.
    """
    directory = Path(directory)
    if not directory.exists():
        return []
    out = []
    for path in sorted(directory.glob(pattern)):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_bytes().decode("cp1252", errors="replace")
        except OSError:
            continue
        stamp = time.strftime(
            "%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(path.stat().st_mtime)
        )
        out.append(
            Response(url=f"file://{path}", status=200, text=text, retrieved_at=stamp)
        )
    return out
