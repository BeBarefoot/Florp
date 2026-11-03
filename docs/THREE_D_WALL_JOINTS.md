# 3D wall end-cap correction — 3 November 2026

Inspected the supplied garden `report(4).json` (1306 by 408 source pixels,
32 walls, 11 opening records) and `florp-plan.glb` (32 wall groups, 56 meshes).
The report contains calibrated, corrected geometry; the rejected opening is
not a physical cut. No re-extraction of this corrected plan is required.

## Cause supported by code

PlanCanvas draws wall strokes with `strokeLinecap="square"`, extending each
end by half its wall thickness. `wallPieces()` previously emitted box chunks
ending at the centreline endpoints. Therefore corners and small endpoint
separations could look closed in the editor but remain separated in both the
live 3D viewer and GLB export. The supplied bottom wall segments also include
separate endpoints about 3.5 source pixels apart, illustrating why node-sharing
alone would not resolve the display discrepancy.

## Change

The shared `wallPieces()` helper now adds square end caps to solid end slabs.
Each cap is limited to half the source wall thickness, matching the editor's
cap convention. It never adds a cap at an interior opening cut. Saved nodes,
wall centreline lengths, opening offsets/widths, calibration, materials and
height parameters are unchanged. Both Plan3D and exportPlan3D already consume
this helper, so they receive the same correction.

Before adding material, construct the oriented footprints of all confirmed
openings. Limit each cap's reach at its first contact with one of those voids,
using separating-axis intervals for sloped as well as axis-aligned walls.
Split cap slabs at opening sill/top heights so a lintel can join without
closing the doorway below it. This guards neighbouring walls' openings as
well as the capped wall's own openings.

This is bounded end-cap construction, not a topology solver that bridges
arbitrary wall gaps. Separate wall IDs/meshes remain; this does not certify a
single watertight/manifold mesh for fabrication. No dependencies, model weights,
cloud services or license-bearing packages were added. Extraction and saved
corrections, including the accepted farmhouse, are untouched.

## Validation scope

Read the supplied JSON/GLB structure and reviewed code. Per the user's standing
instruction, no tests, browser runs, extraction trials or builds were run; CI
is skipped. The new geometry was not rendered or runtime-verified here.

To inspect locally, update the frontend, reload the saved corrected garden
revision, and export a new GLB. Previously downloaded GLBs do not update.
