# What no registry covers

Stage 1 and stage 2 select for testing paperwork. They say nothing about the
two things in your original request that matter most once health is
established: whether the dog is well adjusted, and whether it is beautiful.
Those have to be established by you. Here is the shortest path.

## Well adjusted

Temperament in this breed is driven by three things a registry does not
record: what the parents are like, how the litter was raised for eight weeks,
and how well the breeder matched a specific puppy to you.

The tool reads the breeder's site for named rearing practice and quotes what
it finds. Treat those quotes as claims, not facts. Confirm them by asking:

1. **Where do litters live?** You want "in the house, in traffic", not a
   whelping barn. Ask what room, and ask to see it on video if you cannot
   visit.
2. **What curriculum, and what does it actually consist of?** Puppy Culture
   and Avidog are the common named ones. A breeder running either can tell
   you what they do in week three versus week six without hesitating. One who
   only has the logo cannot.
3. **How are puppies matched to homes?** The answer you want involves
   temperament assessment and the breeder assigning puppies. Litter pick by
   deposit order is a worse sign than most people realize.
4. **What do the parents do all day?** Adult dogs living as pets in the house
   is the single best predictor. Ask to meet the dam. If the dam is not
   available to meet, ask why.
5. **How many litters a year, and how many dams?** A program running many
   simultaneous litters cannot be raising any of them underfoot, whatever the
   website says.
6. **What happens if it does not work out?** A real take-back clause, for the
   life of the dog, is standard among serious breeders.
7. **Who have they placed with that I can call?** Ask for two owners of adult
   dogs, not puppies. An adult owner can tell you how the coat matured and
   how the dog settled.

## Beautiful

This tool scores nothing for appearance, on purpose. A number attached to
"beauty" derived from marketing copy would look like evidence while carrying
none.

What to do instead:

- **Look at adults, not puppies.** Every shortlist card links the breeder's
  adult-dog pages. Australian Labradoodle coats change substantially between
  eight weeks and two years, and puppy photos tell you almost nothing.
- **Ask for photos of both parents at two-plus years**, standing, in profile,
  not posed on a couch.
- **Compare against the ALAA breed standard** rather than against your
  favorite Instagram dog: proportion slightly longer than tall, a level
  topline, and the coat texture you want named explicitly as fleece or wool.
  Fleece and wool shed differently and mat differently.
- **Decide what you actually want before you look**, because you will
  otherwise rationalize whatever the available litter looks like. Write down
  coat type, color range and size target, then hold the list to it.

## The check that is worth the most

Run the OFA lookups. Every card links them. Take the registered names of the
sire and dam off the breeder's own site, search OFA, and confirm the hip and
elbow clearances exist and read the way the breeder says they do.

This takes about ten minutes per breeder and it is the only step in the whole
protocol that does not depend on a membership organization's word. Record the
result:

```json
{ "draycot meadows": { "ofa_verified": true, "notes": "OFA hips Good both parents, checked 9/18" } }
```

in `data/manual/notes.json`, and the next run will score it.

## What to do with a thin shortlist

A protocol this strict can leave one or two names nationally, or none. That is
information, not failure, and it is why the report keeps a near-miss list.

Read the near misses before you conclude the bar is empty. An ALAA Platinum
breeder who simply is not a WALA member has not failed a quality test: WALA
membership is a separate business decision. The breeders who clear two of
three bars are usually where the real choice is, and dual registry
membership correlates at least partly with willingness to pay two sets of
dues.
