# Florp delivery roadmap — accuracy first

**Product goal:** Upload a full PNG/JPG/PDF floor plan and obtain a trustworthy, editable 2D architectural model in one pass. The system should usually need no manual correction, but offer lightweight guided corrections and save quality-reviewed examples for model improvement. A convincing 3D render is *not* a substitute for accurate 2D geometry.

## Gate 1 — reliable 2D architectural extraction (current highest priority)

- [x] Preserve full original plan pixels; prevent destructive crops and log input hash.
- [x] Run YOLO and Yytsi against the same preview; retain model disagreements.
- [x] Prioritize YOLO structural wall axes, deduplicate corroborating segmentation lines, preserve Yytsi-only possibilities for review.
- [ ] Implement canonical connected wall graph: shared junction IDs, wall thickness, exterior/interior type, holes/openings, floor/room faces.
- [ ] Snap and extend ONLY with mask/pixel/dimension support; never connect across a valid opening.
- [ ] Recover bottom/perimeter walls and partition walls without creating false dimension/furniture walls.
- [ ] Connect detected doors/windows to correct wall spans and measure from drawing annotations automatically.
- [ ] Automatically infer drawing scale from OCR/vector/dimension chains, surface only conflicts for user confirmation.
- [ ] Replace verbose advanced controls with one focused **Review next uncertain feature** panel; include move/remove/split/add actions, undo, and mobile-friendly tap/drag.
- [ ] Build a held-out benchmark of representative clean PDFs and scanned/image plans, with verified walls, shared junctions, windows, doors, rooms, metric dimensions, and explicitly labeled negatives.
- [ ] Report pre-correction polygon IoU, wall precision/recall, opening recall and placement error, connected-room accuracy, calibration success, 2D correction time and P90 usability.
- [ ] Target on *supported benchmark inputs*: ≥90% acceptable initial geometry after ≤5 min lightweight corrections, with an aspirational one-pass/no-edit workflow. Thresholds are targets, not measured claims.
- [ ] Train/fine-tune only after evaluation shows repeatable recognition failures that geometry reconstruction cannot solve; retain separate held-out plans and include model/review provenance.
- [ ] Block **Verified architecture** if openings, scale, or critical topology remain unresolved; show specific review items instead.

### Release gate

Do not mark 2D extraction trusted merely because a 3D preview looks plausible. Advance when held-out test cases establish acceptable geometry, topology, openings, scale, and correction time. Record per-model versions and regression tests.

## Gate 2 — verified 3D and viewpoint system

- [ ] Generate 3D ONLY from the approved canonical wall/opening graph.
- [ ] Maintain wall positions, thickness, door/window geometry and levels exactly; flag unknown sill/ceiling elevations for review.
- [ ] Add touch-friendly 3D navigation and viewpoint placement (camera target, height, field of view, heading), stable saved camera nodes.
- [ ] Render depth, normals, line/edge and structural masks from a locked camera for image generation.
- [ ] Add robust scene/model comparison tests so 2D and 3D geometry cannot silently diverge.

## Gate 3 — simple mobile-first user experience

**Primary journey:** Upload image/PDF or take photo → auto-extract 2D → very short review of uncertain architecture only → see generated 3D → choose camera/viewpoint → choose style or give natural-language instructions → generate interior design image → refine style while geometry and camera stay fixed.

- [ ] Implement responsive mobile-first web app/PWA initially; native app only when device capability/usage justifies it.
- [ ] Keep one action per screen, large touch targets, pinch/pan, meaningful progress, simple undo.
- [ ] Make advanced model comparison/training diagnostics accessible to developers but invisible in normal homeowner flow.
- [ ] Save projects, model versions, corrections, camera nodes, style state and rendered versions.

## Gate 4 — photorealistic design generation

- [ ] Integrate one real image-generation backend with control images/geometry-preserving masks.
- [ ] Validate structural consistency before showing a result; never claim depth guidance guarantees exact windows.
- [ ] Retain geometry/camera and let users iterate materials, colors, furniture, lighting and creative styles.
- [ ] Measure image costs, failure rates, latency and iterative consistency.

## Engineering sequencing

1. Finish YOLO-first shared-wall topology and opening recovery.
2. Build a labeled benchmark and rapid correction/review loop in parallel.
3. Close Gate 1 using measured accuracy, not screenshots.
4. Develop Gate 2 and mobile/PWA shell once geometry data contracts stabilize.
5. Add image-generation workflow with locked camera and structural validation.

**Local-first cost policy:** Prefer free tiers, local OCR/segmentation and SQLite during development. Paid APIs only where needed for production-like generation or comparison. Developer labor excluded from cash budget.
