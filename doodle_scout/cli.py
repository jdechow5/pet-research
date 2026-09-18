"""Command line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .config import PROJECT_ROOT, Config
from .dom import parse
from .http_client import FetchError, HttpClient, load_saved_pages
from .protocol import run as run_protocol
from .report import write_outputs
from .sources import alaa as alaa_source
from .sources import wala as wala_source


def build_client(config: Config, args) -> HttpClient:
    return HttpClient(
        user_agent=config.get("http.user_agent", f"doodle-scout/{__version__}"),
        cache_dir=PROJECT_ROOT / "data" / "cache",
        min_interval=float(config.get("http.min_seconds_between_requests", 2.0)),
        timeout=int(config.get("http.timeout_seconds", 30)),
        max_retries=int(config.get("http.max_retries", 3)),
        cache_ttl_hours=0 if getattr(args, "refresh", False)
        else float(config.get("http.cache_ttl_hours", 12)),
        respect_robots=bool(config.get("http.respect_robots_txt", True)),
        offline=bool(getattr(args, "offline", False)),
    )


def cmd_run(args) -> int:
    config = Config.load(args.config)
    client = build_client(config, args)
    if args.selftest:
        from .testing import FixtureClient

        client = FixtureClient()
        print("Running against bundled fixtures. No network requests.\n")

    saved_root = PROJECT_ROOT / "data" / "raw"
    alaa_saved = saved_root / "alaa" if args.from_saved else None
    wala_saved = saved_root / "wala" if args.from_saved else None

    result = run_protocol(
        client,
        config,
        alaa_saved_dir=alaa_saved,
        wala_saved_dir=wala_saved,
        manual_path=PROJECT_ROOT / "data" / "manual" / "notes.json",
        read_sites=not args.no_sites,
        regions=[r.strip().upper() for r in args.regions.split(",")] if args.regions else None,
        site_page_budget=args.site_pages,
    )

    print("Funnel")
    for entry in result.funnel:
        print(f"  {entry['remaining']:>5}  {entry['stage']}")
    print()
    if result.shortlist:
        print("Shortlist")
        for index, candidate in enumerate(result.shortlist, start=1):
            print(
                f"  {index}. {candidate.kennel} ({candidate.region or '??'}) "
                f"score {candidate.score:g} | {candidate.size.verdict.value}"
            )
    else:
        print("Shortlist is empty. Check the funnel and the run notes: a zero")
        print("here often means a source did not parse, not that the bar is empty.")
    if result.needs_confirmation:
        print(f"\n{len(result.needs_confirmation)} pairing(s) need your confirmation.")

    written = write_outputs(result, Path(args.out))
    print("\nWrote:")
    for kind, path in written.items():
        print(f"  {kind:5} {path}")
    print(f"\nOpen {written['html']} in a browser.")
    return 0


def cmd_diagnose(args) -> int:
    """Show what the parsers see. The first thing to run when a count looks wrong."""
    config = Config.load(args.config)
    client = build_client(config, args)

    if args.file:
        responses = load_saved_pages(Path(args.file).parent, Path(args.file).name)
        if not responses:
            print(f"Could not read {args.file}", file=sys.stderr)
            return 1
        response = responses[0]
    else:
        try:
            response = client.get(args.url)
        except FetchError as exc:
            print(f"Fetch failed: {exc}", file=sys.stderr)
            print(
                "\nIf the host is blocking automated requests, open the page in a\n"
                "browser, save it into data/raw/alaa/ or data/raw/wala/, and run\n"
                "  python3 -m doodle_scout run --from-saved",
                file=sys.stderr,
            )
            return 1

    document = parse(response.text)
    print(f"URL      {response.url}")
    print(f"Bytes    {len(response.text):,}")
    title = document.find("title")
    print(f"Title    {title.text if title else '(none)'}")
    print(f"Tables   {len(document.find_all('table'))}")
    print(f"Forms    {len(document.find_all('form'))}")
    print(f"Selects  {len(document.find_all('select'))}")
    print(f"Images   {len(document.find_all('img'))}")

    alaa_records = alaa_source.parse_listing(response, response.url)
    print(f"\nALAA parser found {len(alaa_records)} record(s)")
    for record in alaa_records[:8]:
        print(f"  - {record.kennel} | {record.location} | awards={record.awards}")

    wala_records = wala_source.parse_breeder_page(response)
    print(f"\nWALA parser found {len(wala_records)} record(s)")
    for record in wala_records[:8]:
        print(f"  - {record.registry_id} | {record.kennel} | {record.location} | {record.awards}")

    if not alaa_records and not wala_records:
        print(
            "\nNeither parser matched. Most likely causes:\n"
            "  1. the listing is rendered by JavaScript (save the page from a\n"
            "     browser instead, which captures the rendered DOM), or\n"
            "  2. the page shape changed. Grep the saved HTML for a kennel name\n"
            "     you know is listed and adjust the anchors in\n"
            "     doodle_scout/sources/."
        )
    return 0


def cmd_init(args) -> int:
    for relative in ("data/raw/alaa", "data/raw/wala", "data/cache", "data/manual", "out"):
        (PROJECT_ROOT / relative).mkdir(parents=True, exist_ok=True)
    notes = PROJECT_ROOT / "data" / "manual" / "notes.json"
    if not notes.exists():
        notes.write_text(
            '{\n'
            '  "_about": "Facts only you can establish. Keys are kennel names, lowercased.",\n'
            '  "example kennel": {\n'
            '    "ofa_verified": false,\n'
            '    "exclude": false,\n'
            '    "notes": "called 9/14, waitlist opens in spring"\n'
            '  }\n'
            '}\n'
        )
        print(f"Created {notes}")
    print("Ready. Next: python3 -m doodle_scout run")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="doodle_scout",
        description="Run a national Australian Labradoodle breeder search "
        "protocol: ALAA Platinum, crossed with WALA rating, filtered to "
        "standard-size programs.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", default=None, help="path to a config JSON")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="run the full protocol")
    run_parser.add_argument("--out", default=str(PROJECT_ROOT / "out"))
    run_parser.add_argument("--from-saved", action="store_true",
                            help="parse pages you saved into data/raw/ instead of fetching")
    run_parser.add_argument("--no-sites", action="store_true",
                            help="skip reading breeder websites (faster, no size verdicts)")
    run_parser.add_argument("--regions", default="",
                            help="limit to states, e.g. OR,WA,ID (default: national)")
    run_parser.add_argument("--site-pages", type=int, default=7,
                            help="max pages to read per breeder site")
    run_parser.add_argument("--offline", action="store_true",
                            help="use only the local cache; never touch the network")
    run_parser.add_argument("--refresh", action="store_true",
                            help="ignore cached pages and refetch")
    run_parser.add_argument("--selftest", action="store_true",
                            help="run against bundled fixtures to verify the pipeline")
    run_parser.set_defaults(func=cmd_run)

    diag = subparsers.add_parser("diagnose", help="show what the parsers see on a page")
    source = diag.add_mutually_exclusive_group(required=True)
    source.add_argument("--url")
    source.add_argument("--file")
    diag.add_argument("--offline", action="store_true")
    diag.add_argument("--refresh", action="store_true")
    diag.set_defaults(func=cmd_diagnose)

    init_parser = subparsers.add_parser("init", help="create the working directories")
    init_parser.set_defaults(func=cmd_init)

    args = parser.parse_args(argv)
    return args.func(args)
