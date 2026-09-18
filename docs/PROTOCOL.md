# The protocol, as implemented

Three stages, run in this order, each one narrowing the list.

| Stage | Source | What it filters on |
|---|---|---|
| 1 | ALAA member breeder search on `ilainc.net` | Holds a Platinum Paw |
| 2 | WALA rating pages | Holds a current WALA rating |
| 3 | The breeder's own website | Breeds standard size |

The tool records the count after every stage. That number is most of the
value: the point of the protocol is to find out how far a national list
collapses under two independent rule sets plus a size constraint.

## Two corrections to the protocol as originally written

### 1. WALA "All Star" is a retired rating

The original step 2 said to cross-filter for **WALA All Star**. All Star came
from WALA's **Star Rewards Program**, which WALA restructured into the
**Diamond Rewards Program**, with One, Two and Three Diamond levels. WALA
moved the old program to a page pathed `/old-star-program`, and Star Rewards
badges stopped being valid on member websites after April 2026.

Consequences for the search:

- Filtering on All Star today selects a snapshot of who cleared a bar that no
  longer exists, not who clears the current one.
- A breeder site still showing a Star badge is showing an expired credential.
  That is worth noticing on its own.
- The current equivalent of "the highest WALA bar" is **Three Diamond**.

So this tool treats Diamond as the live rating and All Star as a legacy
signal, scored lower, with a followup attached telling you to ask the breeder
for their current Diamond level. Both are configurable in
`config/search.json` under `protocol.stage_2_wala`. If you want the original
protocol exactly, set `accepted_ratings` to `["All Star"]`.

### 2. ALAA Platinum is a health-testing award, not a breeder tier

Platinum Paw means: OFA final hip and elbow scores, or PennHIP plus OFA final
elbows, for **every** breeding dog in the kennel over age 2, completed by 30
months, maintained continuously. Higher tiers of the Paw Reward Program also
involve eye exams by a board-certified ophthalmologist, a cardiologist
evaluation, and genetic panels.

That is a real and fairly demanding filter, and it maps well onto
"healthiest". It does not map onto "most beautiful" or "well adjusted" at
all. Neither does WALA Diamond, which adds testing breadth, breeder education
and elective practices. Nothing in either registry certifies how a puppy was
raised.

This is why the tool has a stage 3 that reads the breeder's own site, a
signal set covering rearing practice, and a section in the report stating
plainly what it cannot measure.

## What each stage actually proves

**Stage 1 proves paperwork was submitted and accepted.** ALAA is a membership
organization acting on documents its members provide. The award is real, but
the verification is not independent.

**Stage 2 proves a second organization accepted its own paperwork.** Holding
both is meaningfully harder than holding either. It is still two membership
bodies, not two audits.

**Stage 3 proves the breeder says they breed standards.** Size claims come
off marketing copy. The tool quotes the sentence so you can see what it read.

**The one independent check is OFA.** The Orthopedic Foundation for Animals
runs a public database and is the primary record for hip, elbow, eye and
cardiac clearances. Every shortlist card carries links to run that check
against the individual breeding dogs. Until you do it and record the result
in `data/manual/notes.json`, the `ofa_verified` signal scores zero. It is
weighted as heavily as the Platinum award itself, because it is the only
signal in the tool that does not require trusting a registry.

## Cross-registry matching

ALAA and WALA assign their own ids and share no common key, so the two lists
have to be joined on kennel identity. The tool joins on, in order of
strength: shared website domain, shared phone, shared email, then kennel name
similarity with state agreement required.

A false join is the worst thing this tool could do, because it would credit a
breeder with a credential they do not hold. So a name-only match without an
agreeing state is never asserted. It goes to the "Needs your confirmation"
section of the report with the evidence and the runners up, and you decide.
Thresholds live in `config/search.json` under `matching`.

## Sources

- ALAA member breeder search: <https://ilainc.net/guest/breedersearch.aspx>
  (same application at <https://breeders.alaa-labradoodles.com/guest/breedersearch.aspx>)
- ALAA Health Testing and Paw Reward Program:
  <https://alaa-labradoodles.com/for-breeders/paw-reward-program/>
- ALAA breed standard, including the size bands:
  <https://alaa-labradoodles.com/for-breeders/breed-standard/>
- WALA Diamond Rewards Program:
  <https://www.walalabradoodles.org/about-wala/diamond-rewards-program>
- WALA archived Star Rewards Program:
  <https://www.walalabradoodles.org/old-star-program>
- WALA legacy All Star list:
  <https://www.walalabradoodles.org/walabreeder-1/all-star-breeders-of-labradoodles>
- OFA public database: <https://ofa.org/advanced-search/>

Registry status changes daily. The ALAA listing regenerates every 24 hours.
Re-run before you act on anything here.

## Size bands (ALAA breed standard, height at wither)

| Size | Height | Typical adult weight |
|---|---|---|
| Miniature | 14 to 17 in | 15 to 30 lb |
| Medium | 17 to 21 in | 30 to 45 lb |
| Standard | 21 to 24 in | 50 to 65 lb |

Most Australian Labradoodle programs are mini and medium, which is why stage
3 cuts hardest.
