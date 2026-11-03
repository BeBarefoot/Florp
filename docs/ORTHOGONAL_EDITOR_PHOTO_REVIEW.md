# Orthogonal editing and reviewed photo corrections

3 November 2026. Based on the supplied garden before/after screenshots and
second-floor correction export (`report(5).json`, revision 58, 992 by 440).
This is a code and saved-data review, not a runtime accuracy report.

## Evidence

The corrected floor contains 56 walls, including eight user-created walls,
and 16 opening records, including five user-created openings and two rejected
proposals. Several manual walls are slightly diagonal. One doorway host runs
from approximately (227, 256) to (277.8, 248), demonstrating that independent
endpoint snapping overrides the intended horizontal alignment. These numbers
describe the supplied report only; no plan coordinates are used in the engine.

The screenshots also show missing pale partitions/returns, inappropriate
opening proposals, and external annotation fragments. A correction export is
useful evidence, but is not proof that every remaining extracted item is right.

## Editor changes

- Wall creation locks to the dominant horizontal or vertical axis without Shift.
- Resolve the starting anchor first. The second anchor may use an aligned node
  or an actual intersection with another wall, rather than an off-axis corner.
- Preview and length readout use the same placement resolver as the saved edit.
- Snapping does not split through an existing non-rejected opening, which would
  clamp its hosted width to a shorter segment.
- Dragging a node propagates x through its vertical chain and y through its
  horizontal chain. The drag-start geometry determines those chains, avoiding
  orientation changes halfway through a gesture. Reject collapse/reversal.
- Reproject openings on every affected host. Undo/autosave use the existing edit
  path. Measurements and perspective corners retain their independent controls.

Existing saved plans are not automatically straightened on load. A wall joined
to off-axis old geometry may end on a host intersection rather than its old
corner. Only walls affected by an edit are changed; this is not a global
rectification or a rewrite of uploaded corrections.

## Photo extraction changes

- Use pale material evidence and locally verified wall bands when deciding
  whether an opening is empty. The stricter red seed mask previously disagreed
  with pale-wall recovery and could classify its outlines as window rails.
- Require source material at both ends of a photo opening. Parallel ink alone
  cannot establish an opening in an arbitrary missing-wall span. Local windows
  within a broader incomplete gap must satisfy their own jamb checks.
- Inspect the union of paired boundary proposal ranges when their extrapolated
  faces remain parallel and within the width limit. Retain the prior overlap
  otherwise. Per-pixel colour, outline and outside-paper evidence still decides
  which portions become walls; this does not bridge blank spans.

The monochrome/dark-wall extraction branch is unchanged. No saved corrections,
model weights, scale references, export units, or 3D meshing were modified.
There are no new dependencies or cloud calls.

## Validation and limits

No tests, builds, extraction runs, browser sessions or CI runs were performed,
as requested. Changes were inspected in source and against the supplied saved
report. No claim of complete recovery, absence of regressions or measured
speed is made. Very faded jambs can remain unresolved; walls not proposed by
the boundary detector can still be missed. The garden and floor must be
checked by the user, and the accepted farmhouse remains a comparison case.

After updating main, restart the API and frontend. Drawing changes apply to
existing saved plans. Extraction changes apply only to a new extraction; use
a separate upload to compare without replacing the corrected draft.
