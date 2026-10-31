# Focused extraction diagnostics — 31 October 2026

Status: partial corrections, **photographed yard extraction remains unacceptable**. This is not an extraction-accuracy certification or a completed production release.

## Procedure and scope

Baseline: main at `8377048b57f525373998c23d59e73fab2d43e2ad`. Ran the real local extraction worker on the supplied original yard photograph (1794×630), floor photograph (1996×894), and farmhouse scan (2048×1068). Inspected structural masks, rejected pixels, raw geometry, and the reconstructed PlanModel. The worker used the default deterministic path; the optional object detector was unavailable. No checkpoints were downloaded, no generative models were used, and no metric scale was invented.

The user explicitly authorized these focused extraction/debug runs. Automated test suites, builds, browser tests, and app walkthroughs were not run. CI is skipped for this patch.

## Confirmed findings and corrections

- The compact-symbol rule classified the actual yard upper-left red wall corner as text. Apply that rule to neutral/solid layers, not red hatch components.
- Red dimension glyphs survived hatch closing, and their stroke widths influenced wall-width estimation. Identify compact glyph-like loops before fusion and repeated loops afterwards. Exclude tiny hatch pinholes and larger room holes. This remains a heuristic and does not remove all annotation strokes.
- The run extractor's minimum length and aspect rule could omit short colored-wall returns before graph construction. Use the smaller colored-plan run budget while retaining the existing dark-plan budget.
- Stub pruning used the house-wide median thickness, penalizing thin partitions. Use the smaller of local and median thickness for that edge's length budget.
- The existing debug script rendered raw worker objects only. Add `model.json`, `model-clean.png`, `model-overlay.png`, `model.svg`, and `debug_stats.json` to distinguish mask failures from graph/reconstruction failures. Existing outputs remain available. The model images include hosted proposed openings; they are diagnostic, not approved architecture.

## Direct comparisons

On the yard source, exact red-mask pixel counts in explicitly inspected source-pixel regions were:

| Region (left, top, right, bottom) | Baseline | Corrected |
|---|---:|---:|
| Upper-left corner (375, 80, 435, 120) | 72 | 1390 |
| Red `500` label (550, 0, 710, 65) | 4386 | 1121 |
| Red `300` label (185, 145, 300, 205) | 2874 | 0 |

These are retention/noise observations for the named regions, not precision/recall against a gold dataset. Coordinates are used only for the diagnostic comparison; none are hardcoded into the engine.

The farmhouse raw Document and the reconstructed nodes, walls, and openings were exactly equal to their baseline equivalents. The fireplace remains unclassified. A broader no-regression guarantee is not established.

Final single-run cold worker times in this container were yard **1.671 s**, floor **1.628 s**, farmhouse **1.275 s**. These measurements exclude debug rendering, API/network/UI time, and do not guarantee latency on other hardware. Raw wall/fragment counts are not accuracy scores.

## Unresolved

- Yard top-window rails are weak/inconsistent across a long gap containing multiple windows and landscaping occlusion. One merged span does not reliably expose two rails to the current gap classifier.
- Red dimension bars and characters attached to real structural components remain. Isolated-loop suppression does not solve text attached to walls.
- Some annotations still produce false wall and opening candidates. The photographed floor is improved but is not complete or verified.
- Some source geometry is physically obscured by yellow landscaping symbols or cropped at the page edge. The cleaned generative reference visually completes those regions, but it cannot certify their original coordinates.
- Width/junction consolidation can still distort or merge short photographed segments. Additional numeric threshold tuning is not evidence of semantic correctness.

Do not describe the yard as solved. These diagnostics support the named fixes only.

## Repeat locally

From `apps/api`, run:

```sh
uv run python scripts/evaluate_workspace.py --image /absolute/path/to/plan.png --output /tmp/florp-photo-check --runs 1 --debug
```

Inspect `debug_strips.png` first, then `model-overlay.png`. Missing mask pixels require a segmentation correction; retained pixels missing from the reconstructed model require a topology correction. Annotated source files and diagnostic images are not committed to the repository.
