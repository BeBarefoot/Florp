# Investigation from the supplied corrected exports

Inputs: first export set (`report.json`, `geometry.geojson`, SVG, DXF, PNG)
is the second-floor plan; the `(1)` set is the yard plan. Read the original
source-coordinate PlanModel embedded in each report; exported geometry is in
local centimetres with a translated 50 cm viewport. Metric export coordinates
must not be compared directly with image coordinates.

## Findings supported by the supplied files

- Floor: revision 57, 992 by 440 source, 49 walls, including 8 user walls;
  14 openings, of which 9 have user-created IDs. Several added walls host
  doors/windows. These are missing opening detections/hosts, not missing
  solid masonry to be filled across the void.
- Yard: revision 59, 1306 by 408 source, 26 walls, including 8 user walls;
  6 openings, of which 5 have user-created IDs. The added top wall hosts two
  windows and a door. Its voids must remain distinct from solid wall recovery.
- The yard's saved automatic envelope is strongly indented through the top
  building region, including the area of the added top host. It is unsuitable
  as a crop boundary for recovering the missing geometry.
- Retained extracted marks are not necessarily approved structural truth.
  For example, the floor export still includes detached exterior red bars.
  These files are correction evidence, not an exhaustive clean segmentation
  dataset or a certificate that every retained entity is correct.

## Implementation

1. For coloured plans only, an inferred envelope no longer clips extraction
   or establishes exterior-opening semantics. Return no automatic envelope in
   this case. An explicitly submitted building outline remains authoritative.
   The dark-plan/farmhouse envelope path is unchanged.
2. Coalesce nearly collinear boundary proposals before pairing their faces.
   Keep the longest proposal's equation instead of repeatedly averaging it.
   This lets fragmented opposite faces overlap. Pixel support is still checked
   locally and unsupported windows/doors split the result; proposal gaps are
   not filled automatically.
3. Enable photographed-opening processing for every coloured plan, even if
   no new boundary pair was recovered. Use local-contrast neutral strokes for
   pale opening symbols, retaining the continuous arc and leaf requirements.
4. Probe door hinges at the centreline and either wall face. Evidence-probe
   offsets do not move or resize the emitted physical opening/host.
5. When full-gap window rails fail, find individually supported frame spans
   inside the gap. Validate parallel rails and minimum separation for each
   span; exclude continuous wall tint. Create hosts only for those spans,
   rather than stretching a window across an entire missing wall interval.
6. Apply locally supported annotation-bar rejection independently of positive
   wall recovery elsewhere in the image. Existing glyph filtering remains.

No coordinates, entity IDs, measured lengths, or plan-specific templates from
these files are embedded in the extractor. Calibration and export dimensions
are unchanged. Existing corrected revisions are not modified automatically.

## Validation status

Investigation consists of reading the supplied exports and reviewing code.
No tests, extraction trials, builds, browser runs or CI were run, as requested.
Runtime accuracy, latency and regression results remain unverified. The
farmhouse dark-wall branches are unchanged by construction, not demonstrated
equivalent by a fresh run. Re-extraction replaces a draft through the existing
revision/history flow; the supplied correction revisions remain the reference.
