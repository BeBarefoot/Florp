# Second-floor follow-up — 1 November 2026

Reviewed the supplied `report(3).json` embedded PlanModel (992 by 440, revision
66), against the preceding correction export. The new edited revision contains
46 walls (45 marked extracted, one user-created) and 12 openings (10 extraction
IDs, two user-created IDs). Counts and IDs describe the edited export, not
an accuracy score or proof that all retained entities are correct.

The remaining user-created entities are a top-right window on an existing host
and a vertical Mamad entry door on a newly drawn host. The door lane is bounded
by end caps of two horizontal walls. The existing gap enumeration starts from
collinear runs and seeks perpendicular walls; it does not enumerate a missing
vertical lane solely from two horizontal wall end caps.

## Changes

- On coloured plans, add candidate lanes between sufficiently aligned end caps
  of parallel walls. Subtract jamb half-thicknesses from the longitudinal span.
  Candidates still need source frame rails or continuous door arc plus leaf
  evidence; an aligned endpoint pair alone never creates an opening.
- Carry observed source support on the resulting opening and its virtual host.
  This retains corroborated short hosts through the existing support-aware
  pruning rule instead of treating them as unsupported isolated fragments.
- For these photo openings, reject reconstructed host candidates that cannot
  cover their source span (apart from one-pixel endpoint tolerance). Prefer full
  coverage before perpendicular proximity. If no full host survives, retain an
  unhosted proposal rather than silently truncating the opening onto a short
  neighbouring fragment.
- Do not expand these locally observed spans to a larger reconstruction gap.
  Synchronize their hosted span with the emitted offset and width. Dark-plan
  opening/host selection and gap expansion use their previous paths.

The changes use no reference coordinates or plan-specific IDs. Calibration,
saved user corrections, editor operations and farmhouse extraction are not
modified by this patch. The supplied exports are investigation inputs only.

## Verification scope

Read the correction reports and reviewed code. No tests, extraction trials,
builds, browser runs or CI were executed, as instructed. Runtime improvement,
latency and no-regression remain unverified. This is an implemented correction
for the identified enumeration and hosting cases, not an accuracy certification.
