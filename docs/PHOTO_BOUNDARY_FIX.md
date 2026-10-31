# Coloured-plan boundary recovery

This patch targets the yard photograph and second-floor photograph. It is
implemented but **not runtime-verified**. At the user's request, no tests,
extraction trials, builds, or browser runs were performed. There are no new
accuracy or timing measurements and no demonstrated no-regression result.

## Changes

- After the existing dark-wall/coloured-wall decision, coloured plans get a
  local boundary-pair recovery pass. It samples the actual sloping boundaries,
  red interior, and neighbouring paper rather than requiring an entire
  connected hatch component to pass one outline-density threshold.
- Supported intervals fill the wall between observed faces, including thin
  partitions. Colourless door/window intervals stay open. Recovery adds to the
  retained legacy walls; a missing boundary proposal does not delete them.
- Solid red bars are removed only with local negative evidence: red interior
  and edges of essentially equal darkness, without darker enclosing outlines.
  A positive wall-boundary match takes precedence over bar rejection.
- Existing glyph filtering remains in place. Newly supported wall regions
  are restored after glyph filtering, so a short return is not lost merely
  because it belongs to a compact component.
- Width estimation uses supported bands and concrete, avoiding red annotation
  strokes as the thickness reference for the new recovery path.
- Observed boundary support travels with raw wall segments to reconstruction.
  Short supported piers/returns are exempt from the generic dangling-stub
  length filter. Unsupported fragments retain the existing pruning rules.
- Coloured-plan windows can use separated edges of a blurred frame when
  thresholded ink yields only one rail. Separation is relative to wall
  thickness; the edges must still span the proposed wall gap.
- Coloured-plan doors require a densely sampled, continuous arc, with evidence
  in every part of its sweep. Red annotation ink is excluded from this arc
  evidence. Existing leaf evidence is still required.

## Farmhouse isolation

The new mask pass is inside the coloured-plan branch, after the original
dark-wall decision. Dark-plan thresholds, morphology, run fitting, extension,
opening thresholds and pruning remain on their previous paths. The new raw
segment `boundary_supported` flag defaults to false, including older saved
documents. This isolates the accepted farmhouse processing by construction;
it is not a substitute for a runtime regression check.

## Review

Re-extract each photographed plan from its original upload after updating the
API. Loading a previously saved model alone does not rerun extraction. Check
perimeter walls, window piers, thin partitions, annotation bars outside the
building and door placements against the original. The cleaned generative
references are visual guidance, not measurement ground truth.

Source coordinates and the existing single-reference calibration are retained.
Nothing is hardcoded to a particular plan, and no models, checkpoints, OCR
services or new dependencies are added. Occluded and cropped geometry remains
limited by the source evidence; the engine does not certify hidden dimensions.
