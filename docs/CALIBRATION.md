# Florp detection calibration

## Evidence layers
- **Grayscale base** removes color noise from colored architectural scans.
- **Raw lines** are optional low-opacity diagnostic strokes, never called walls.
- **Wall candidates** pair long, approximately horizontal/vertical, nearby parallel strokes with significant shared overlap. Very short marks, diagonal furniture edges and some dimension marks are excluded.
- Text/OCR midpoint exclusions reduce some false positives. Missing OCR means this filter is weaker.

## Important limitations
Paired-line detection is a deliberately **conservative heuristic**, not reliable semantic wall recognition. It can still admit tables, cabinets, annotation lines, or miss thin/angled walls. Candidate confidence is heuristic ranking, not calibrated probability. Do not automatically accept candidates or infer windows and doors from gaps.

## Next calibration improvements
1. Curate scanned/color/digital plans and manually label wall centerlines, openings, furniture and dimension graphics.
2. Use a learning-based architectural symbol/line segmentation model after evaluation shows the heuristic is insufficient.
3. Detect dimension chains and drawing layers, suppress measured dimensions/landscape/property boundaries, use wall thickness consistency and connectivity.
4. Estimate orthogonal vanishing orientation / plan rotation and distinguish partitions from furniture with image crops.
5. Benchmark per-class precision/recall on held-out plans, measure editing time, and record user corrections.
6. Add shared node topology constraints, room boundary validity, door and window anchoring and provenance/confidence.
