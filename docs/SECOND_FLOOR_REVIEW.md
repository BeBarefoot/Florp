# Second-floor correction review — 1 November 2026

Input: the supplied `report(2).json` embeds a source-coordinate PlanModel at
992 by 440, revision 43. It contains 38 walls (36 extracted and 2 user-created)
and 15 openings (7 with extraction IDs and 8 with user-created IDs). These
counts describe the supplied edited revision, not measured extractor accuracy.
The corresponding GeoJSON/SVG/DXF/PNG are alternate exports of that revision.

## Findings

The two user-created hosts cover the upper-left exterior side and the vertical
Mamad entry span. Added openings also lie inside continuous extracted runs,
including the first/last top windows and internal door spans. Gap-only opening
enumeration cannot propose these when mask fusion or scan-band union has
already produced a continuous wall run. Adding more solid fill cannot address
this failure.

The report also contains inconsistent source spans versus host offsets. For
example, opening o0 has a source span starting at x=276.5, while its host starts
near x=91.97 and its offset is about 165.88 (placing it near x=257.85). The editor
used relative host-length fractions when moving endpoints and retained stale
span coordinates. Thus a corrected wall endpoint could move an existing
window, and exported diagnostic span data could disagree with rendered cuts.
These coordinates are investigation evidence only, never runtime constants.

## Changes

- On coloured plans, propose sustained colour-free intervals inside continuous
  wall runs as well as gaps between runs. Probe bounded continuations where a
  missing corner leaves the first window outside a surviving run, requiring
  material jamb evidence on both sides. The probe does not extend solid walls.
  Neither creates an opening without
  the existing rail or continuous arc-plus-leaf corroboration.
- Use original material pixels, rather than reconstructed filled strips, to
  mask structural ink out of the photo symbol evidence. Otherwise a falsely
  filled strip hides the symbol needed to correct it.
- Prefer local candidate spans and suppress overlapping accepted openings,
  so the additional pass does not emit duplicate cuts/hosts.
- When editing a wall endpoint, project the old image-space opening centre
  onto the new host and retain physical width instead of moving it by a
  fraction of total wall length. Clamp when the new host cannot contain it.
- Synchronize the source span with the actual host offset/width when adding,
  editing, splitting or reattaching hosted openings. Existing saved revisions
  are not retroactively reinterpreted or overwritten.

No source-specific coordinates, template matching or calibration changes are
introduced. Dark-plan/farmhouse extraction does not enter the new pass. Editor
position preservation applies to edited walls on every plan.

## Validation

Read the supplied report and reviewed source changes only. Per the user's
instruction, no automated tests, extraction runs, browser runs, builds or CI
were executed. Improvement, completeness and no-regression are not certified.
