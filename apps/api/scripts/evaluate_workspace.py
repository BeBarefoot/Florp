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
from app.plan_workspace import Document, footprint
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
            if p.geom_type != "Polygon":
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
    for opening in [o for o in document.objects if o.kind == "window"]:
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


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.runs <= 10:
        parser.error("--runs must be 1..10")
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
        "openings": sum(o.kind != "wall" for o in document.objects),
        "physical_scale_confirmed": document.reference is not None,
        "warnings": document.warnings,
        "accuracy": "Not measured by this script; compare output to independent annotations.",
    }
    (args.output / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
