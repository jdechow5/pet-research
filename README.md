# doodle-scout

Finds standard-size Australian Labradoodle breeders by running one specific
protocol, repeatably, and showing its work.

```
Stage 0   every current ALAA member breeder
Stage 1   filtered to Platinum Paw                 (ALAA's own health-testing award)
Stage 2   cross-filtered against WALA ratings       (a second, independent rule set)
Stage 3   cross-filtered to standard-size programs  (the tightest constraint)
```

Output is a single self-contained HTML page you work out of, plus CSV and
JSON. Every claim on it carries the sentence and the link it came from.

No dependencies. Python 3.9 or newer, nothing to install, no virtualenv.

## Run it

```bash
python3 -m doodle_scout init            # create the working directories
python3 -m doodle_scout run --selftest  # verify the pipeline against fixtures, no network
python3 -m doodle_scout run             # the real thing
open out/shortlist.html
```

Useful flags:

| Flag | Why |
|---|---|
| `--regions OR,WA,ID` | limit to states instead of a national sweep |
| `--no-sites` | skip reading breeder websites (fast, but no size verdicts) |
| `--from-saved` | parse pages you saved from a browser into `data/raw/` |
| `--refresh` | ignore the local cache and refetch |
| `--offline` | use only cached pages, never touch the network |
| `--selftest` | run the whole protocol against bundled fixtures |

Every fetched page is cached for 12 hours, requests are spaced two seconds
apart, and `robots.txt` is honored. The ALAA listing only regenerates every
24 hours, so re-running costs nothing.

## Read this before trusting a run

**The parsers have not been run against the live sites.** They were built and
tested against fixtures matching the documented URL shapes
(`BreederDetails.aspx?id=NNNN&state=XX` for ALAA, `WALA-####-#####` ids for
WALA) and they are written to discover form controls rather than hardcode
them, but the network environment they were written in could not reach either
host. The first live run is the real test.

If a stage count looks wrong, that is the tool telling you something, and
`diagnose` is how you find out what:

```bash
python3 -m doodle_scout diagnose --url "https://ilainc.net/guest/breedersearch.aspx"
python3 -m doodle_scout diagnose --file data/raw/alaa/saved.html
```

It prints what each parser saw and, when it saw nothing, the two likely
causes. The reliable fallback for either registry is to open the listing in a
browser, save it as HTML into `data/raw/alaa/` or `data/raw/wala/`, and run
`--from-saved`. The same parsers run on saved HTML, so a site that blocks
automated requests costs you one manual save, not the feature.

An empty shortlist is never reported as a clean result. The report says so
explicitly and shows the funnel and the near misses, because a zero is as
likely to mean a source did not parse as it is to mean the bar is empty.

## Two things the protocol gets wrong, and what the tool does about it

**WALA All Star is retired.** It came from the Star Rewards Program, which
WALA restructured into the Diamond Rewards Program (One, Two, Three Diamond).
Star badges expired in April 2026. The tool treats Diamond as the live rating
and All Star as a legacy signal, and flags any All Star breeder with a
followup to ask their current Diamond level.

**ALAA Platinum is a hip and elbow testing award, not a general breeder
tier.** It is a strong filter for "healthiest" and says nothing about
temperament or appearance. Full detail and sources in
[docs/PROTOCOL.md](docs/PROTOCOL.md).

## What this tool will not do

It does not score appearance. Coat, structure and expression cannot be read
off a registry listing or a marketing page, and a number invented for them
would look like evidence while carrying none. The report links each
breeder's adult-dog pages instead and leaves the judgement with you.

It does not verify temperament. The rearing signals it collects (raised in
the home, Puppy Culture or Avidog, temperament testing, litter frequency) are
read off the breeder's own copy. They record a claim. Confirm them by
visiting. [docs/VETTING.md](docs/VETTING.md) has the questions worth asking.

It does not assert a cross-registry match it cannot support. Two listings are
only joined automatically on a shared domain, phone or email, or on a name
match that also agrees on state. Everything else goes to a "Needs your
confirmation" section with the evidence.

## The one check worth doing by hand

Both registries are membership organizations acting on paperwork their
members submit. OFA is not: it is the public primary record for hip, elbow,
eye and cardiac clearances. Each shortlist card links the OFA searches for
that kennel. Run them, then record what you found:

```json
{ "draycot meadows": { "ofa_verified": true, "notes": "both parents OFA hips Good, 9/18" } }
```

in `data/manual/notes.json`. It is weighted as heavily as the Platinum award
itself, and it scores zero until you do it.

## Layout

```
doodle_scout/
  dom.py            forgiving HTML tree (stdlib html.parser)
  webforms.py       ASP.NET __doPostBack / __VIEWSTATE driver
  http_client.py    polite cached fetcher, plus the saved-HTML path
  normalize.py      kennel name, domain, state and phone normalization
  resolve.py        cross-registry entity resolution
  size.py           standard-size classification from page text
  score.py          weighted scoring over verifiable signals only
  protocol.py       the three-stage funnel
  report.py         HTML, CSV and JSON output
  sources/
    alaa.py         stage 1
    wala.py         stage 2
    breeder_site.py stage 3 plus rearing signals
    ofa.py          independent verification links
config/search.json  the protocol itself: thresholds, weights, accepted awards
docs/               the protocol in prose, and what to ask a breeder
tests/              57 tests, no network required
```

Change the protocol in `config/search.json`, not in the code. To run the
original protocol exactly as written, set
`protocol.stage_2_wala.accepted_ratings` to `["All Star"]`.

```bash
python3 -m unittest discover -s tests
```
