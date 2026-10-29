# Spatial review implementation and test plan

Continue the Research audit findings flow: review enclosure/rooms and high-impact
conflicts on the plan, with a contextual inspector. Keep all geometry changes
explicit and reversible. Do not infer rooms across missing boundaries.

1. Extend read-only draft quality output with wall-supported face polygons,
   boundary source-wall IDs, shared partition IDs and loose endpoint markers.
   Do not persist inferred faces or certify their architectural semantics.
2. Add a Rooms & gaps review mode in the main drawing, with accessible SVG
   selection, next-gap navigation and an inspector next to the plan.
3. A selected room exposes its boundary walls. Selecting a boundary enters the
   existing wall editor. Drawing a partition uses existing wall creation;
   removing a shared partition merges only the derived review regions and must
   reject any operation that would discard hosted openings.
4. Recompute derived review regions after every draft edit, undo or redo.
   Discard stale quality responses. Keep candidate review accessible separately.

Tests: two adjacent rooms share one partition; removing it produces one face;
open contours produce markers but no fake face; source wall IDs survive graph
splits; main editor room selection and shared-partition removal/undo; keyboard
selection; existing review-to-draft workflows; full backend, typecheck and build.

This is spatial review of closed regions, not semantic room classification or
proof of extraction accuracy. It does not replace persisted graph revision
history or supply missing source-image evidence.
