# Unified plan workspace

Product entry: projects → upload/select plan → `/plan/:id`. Upload opens the new canvas and extraction starts automatically on an empty plan. No dataset, training or apply-to-draft action. Historical editor and saved layouts remain accessible.

One versioned pixel-space document owns wall axes/thicknesses, opening endpoints/hosts, review state and the known-distance reference. Dimensions, net room areas, 3D adapter and metric exports derive from that document. Immutable revisions have optimistic concurrency; stale extraction/save cannot overwrite newer revisions. Re-extraction requires explicit replacement; prior revisions can be restored. Local recovery and failed saves remain visible.

Measurement: click first point, moving line follows pointer, click second point, adjust either endpoint, enter meters/cm, confirm. Image CTM handles zoom. Reference changes scale without changing source geometry. Unknown scale does not prevent extraction/editing; it disables metric export/3D until a reference exists.

Clean/overlay/original views, bounded scrolling canvas, selected-only handles, focused wall/door/window/false classification, two-point additions, host selection, shared junction movement, dependent opening movement, undo/redo, scale persistence, GLB and PNG/SVG/DXF exports are implemented. The export includes the current document and reference for recovery. Required 50cm frame is an export boundary, never architecture.

## Limits that must remain visible

Color extraction and monochrome fallback are not guaranteed to recognize every real wall. Door/window extraction uses the trusted local detector if configured; without local weights deterministic collinear-gap proposals use parallel rails for windows and hinge-localized circular evidence for doors. These are uncertain findings and may require correction. Bounding-box spans remain uncertain findings; no claim that every model box is an exact window footprint. No model downloads or training are initiated.

Flat, uniformly scaled input is required for one-line metric scale. The Source notes panel now provides guided four-corner straightening using confirmed paper proportions (A-series presets or a custom width/height ratio). This creates a new plan, preserves original sources and revisions, stores forward/inverse transforms, and transfers an existing reference when it lies inside the sheet. The new source is automatically extracted. Unknown page proportions and lens distortion cannot be recovered from one known line; no accuracy certification is fabricated.

Exterior classification is provisional. Concrete on the exterior may remain unclassified; the exterior filter is disabled without classified evidence. Isolated diagonal wall runs are retained using rotated component fitting and exposed as reviewable runs. Arbitrary curved or complex connected masks still require source review. Floors require closed supported boundaries; large gaps are not invented. Room derivation uses internal wall faces; only rectangular net polygons get a width/depth pair.

Release accuracy remains empirical: no real-plan ground-truth campaign or 90% accuracy certification has been performed. These empirical accuracy limits remain explicit; implementation tests cannot substitute for independent real-plan accuracy measurements.
