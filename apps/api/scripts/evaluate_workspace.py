"""Run the actual extraction worker and save reproducible source-pixel results.

Example (from apps/api):
  uv run python scripts/evaluate_workspace.py --image /path/plan.png --output /tmp/eval --runs 3

Uses the worker's normal configured provider. No implicit model downloads,
manual geometry corrections, ground-truth claims, or invented metric scale.
"""

from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys, time
from pathlib import Path
import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.plan_workspace import Document, Segment, Point, footprint
from app.plan_reconstruct import reconstruct
from shapely.ops import unary_union


def render(document, source):
    image = np.full_like(source, 255)
    elements = []
    for wall in [o for o in document.objects if o.kind == "wall"]:
        shape = footprint(wall)
        cuts = [footprint(o) for o in document.objects if o.host_id == wall.id]
        if cuts:
            shape = shape.difference(unary_union(cuts))
        color = (140, 75, 30) if wall.material == "concrete" else (100, 100, 170)
        fill = "#1e4b8c" if wall.material == "concrete" else "#aa6464"
        parts = list(shape.geoms) if hasattr(shape, "geoms") else [shape]
        for p in parts:
            if p.geom_type != "Polygon" or p.is_empty:
                continue
            cv2.fillPoly(image, [np.rint(p.exterior.coords).astype(np.int32)], color)
            for hole in p.interiors:
                cv2.fillPoly(
                    image, [np.rint(hole.coords).astype(np.int32)], (255, 255, 255)
                )
            rings = [p.exterior, *p.interiors]
            path = " ".join(
                "M" + " L".join(f"{x:.3f},{y:.3f}" for x, y in ring.coords) + " Z"
                for ring in rings
            )
            elements.append(f'<path d="{path}" fill="{fill}" fill-rule="evenodd"/>')
    for opening in [o for o in document.objects if o.kind in ("window", "garage")]:
        p = footprint(opening)
        cv2.fillPoly(
            image, [np.rint(p.exterior.coords).astype(np.int32)], (220, 180, 90)
        )
        path = "M" + " L".join(f"{x:.3f},{y:.3f}" for x, y in p.exterior.coords) + " Z"
        elements.append(f'<path d="{path}" fill="#5ab4dc"/>')
    overlay = cv2.addWeighted(source, 0.55, image, 0.45, 0)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {document.width} {document.height}"><title>Source-pixel extraction; physical scale unconfirmed</title><rect width="100%" height="100%" fill="white"/>'
        + "".join(elements)
        + "</svg>"
    )
    return image, overlay, svg


def debug_overlays(source, document, out: Path):
    """Per-stage overlays: strips, thin ink, envelope, rejected components by reason, gap classes."""
    from app.ink_layers import wall_strips

    s = wall_strips(source)
    (out / "debug_stats.json").write_text(json.dumps({
        **s.stats,
        "rejected_pixels": {key: int(mask.sum()) for key, mask in s.rejected.items()},
    }, indent=2))
    h, w = source.shape[:2]
    strips = np.full_like(source, 255)
    strips[s.thin] = (210, 210, 210)
    strips[s.dark] = (0, 0, 0)
    strips[s.red] = (0, 0, 255)
    strips[s.blue] = (255, 0, 0)
    cv2.imwrite(str(out / "debug_strips.png"), strips)
    colors = {
        "too_thin": (0, 200, 255),
        "text": (255, 0, 255),
        "no_outline": (0, 180, 0),
        "dashed": (255, 200, 0),
        "decor": (0, 120, 255),
    }
    rej = np.full_like(source, 255)
    for name, mask in s.rejected.items():
        rej[mask] = colors.get(name, (128, 128, 128))
    cv2.imwrite(str(out / "debug_rejected.png"), rej)
    env = source.copy()
    if document.envelope:
        pts = np.array([(p.x, p.y) for p in document.envelope], np.int32)
        cv2.polylines(env, [pts], True, (0, 160, 0), 2)
    cv2.imwrite(str(out / "debug_envelope.png"), env)
    gaps = source.copy()
    kinds = {"door": (0, 0, 230), "window": (230, 140, 0), "garage": (200, 0, 200)}
    for o in document.objects:
        if o.kind in kinds:
            cv2.line(
                gaps,
                (int(o.start.x), int(o.start.y)),
                (int(o.end.x), int(o.end.y)),
                kinds[o.kind],
                3,
            )
    for p in document.passages:
        cv2.circle(gaps, (int(p.x), int(p.y)), 5, (0, 160, 0), 2)
    cv2.imwrite(str(out / "debug_gaps.png"), gaps)

    # The editor displays reconstructed geometry, not raw worker segments.
    # Save both so pixel retention and graph/pruning failures are distinguishable.
    model = reconstruct(document, "diagnostic")
    (out / "model.json").write_text(model.model_dump_json())
    nodes = {node.id: node for node in model.nodes}
    walls = {wall.id: wall for wall in model.walls}
    objects = [Segment(
        id=wall.id,
        start=Point(x=nodes[wall.a].x, y=nodes[wall.a].y),
        end=Point(x=nodes[wall.b].x, y=nodes[wall.b].y),
        thickness_px=wall.thickness_px, material=wall.material,
        height_m=wall.height_m,
    ) for wall in model.walls]
    for opening in model.openings:
        if opening.status == "rejected" or not opening.host_wall_id or opening.width_px < 2:
            continue
        wall = walls[opening.host_wall_id]
        a, b = nodes[wall.a], nodes[wall.b]
        direction = np.array([b.x - a.x, b.y - a.y])
        direction /= np.linalg.norm(direction)
        start = np.array([a.x, a.y]) + direction * opening.offset_px
        end = start + direction * opening.width_px
        objects.append(Segment(
            id=opening.id, kind=opening.kind, host_id=wall.id,
            start=Point(x=start[0], y=start[1]), end=Point(x=end[0], y=end[1]),
            thickness_px=wall.thickness_px, height_m=opening.height_m,
            sill_m=opening.sill_m,
        ))
    reconstructed = Document(width=document.width, height=document.height, objects=objects)
    clean, overlay, svg = render(reconstructed, source)
    cv2.imwrite(str(out / "model-clean.png"), clean)
    cv2.imwrite(str(out / "model-overlay.png"), overlay)
    (out / "model.svg").write_text(svg)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--debug", action="store_true", help="write per-stage overlays")
    parser.add_argument(
        "--gold", type=Path, help="data/gold/<name> directory; writes score.json"
    )
    parser.add_argument(
        "--update-thresholds", action="store_true", help="ratchet gold thresholds up"
    )
    args = parser.parse_args()
    if not 1 <= args.runs <= 10:
        parser.error("--runs must be 1..10")
    gold = None
    if args.gold:
        from app.opening_calibration import load_gold

        try:
            _, gold, identity = load_gold(args.gold)
            if hashlib.sha256(args.image.read_bytes()).hexdigest() != identity:
                parser.error(
                    "The evaluation image does not match the gold snapshot source"
                )
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
    if args.update_thresholds and not args.gold:
        parser.error("--update-thresholds requires --gold")
    args.output.mkdir(parents=True, exist_ok=True)
    result = args.output / "document.json"
    times = []
    for _ in range(args.runs):
        start = time.perf_counter()
        subprocess.run(
            [
                sys.executable,
                "-m",
                "app.workspace_worker",
                str(args.image.resolve()),
                str(result.resolve()),
            ],
            cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"},
            check=True,
            timeout=20,
        )
        times.append(time.perf_counter() - start)
    document = Document.model_validate_json(result.read_bytes())
    from app.deterministic_blueprint.preprocess import decode

    source = decode(args.image.read_bytes())
    clean, overlay, svg = render(document, source)
    cv2.imwrite(str(args.output / "clean.png"), clean)
    cv2.imwrite(str(args.output / "overlay.png"), overlay)
    (args.output / "clean.svg").write_text(svg)
    report = {
        "source_sha256": hashlib.sha256(args.image.read_bytes()).hexdigest(),
        "source_resolution": [document.width, document.height],
        "cold_process_seconds": times,
        "under_5_seconds": all(t < 5 for t in times),
        "under_20_seconds": all(t < 20 for t in times),
        "walls": sum(o.kind == "wall" for o in document.objects),
        "open_passages": len(document.passages),
        "openings": sum(o.kind != "wall" for o in document.objects),
        "physical_scale_confirmed": document.reference is not None,
        "warnings": document.warnings,
        "accuracy": "Not measured by this script; compare output to independent annotations.",
    }
    if args.debug:
        debug_overlays(source, document, args.output)
    if args.gold:
        from app.plan_model import PlanModel
        from app.plan_reconstruct import reconstruct
        from app.plan_score import score, flat_metrics, minimum_thresholds

        result = score(reconstruct(document, gold.id), gold)
        report["score"] = result
        (args.output / "score.json").write_text(json.dumps(result, indent=2))
        if args.update_thresholds:
            flat = flat_metrics(result)
            path = args.gold / "thresholds.json"
            old = minimum_thresholds(
                json.loads(path.read_text()) if path.exists() else {}
            )
            path.write_text(
                json.dumps(
                    {
                        k: round(max(old.get(k, 0), v - 0.02), 3)
                        for k, v in flat.items()
                    },
                    indent=2,
                )
            )
    (args.output / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
