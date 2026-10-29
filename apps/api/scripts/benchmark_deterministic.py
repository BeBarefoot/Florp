"""Reproducible timing contract, including image decoding and output ZIP encoding.

uv run python scripts/benchmark_deterministic.py --runs 5 --output report.json
--image can be repeated to add private real plans without committing sources.
"""

from __future__ import annotations
import argparse
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time
import zipfile

# Pin before importing native libraries; one Tesseract OMP thread per worker.
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
pinned = None
if hasattr(os, "sched_getaffinity"):
    pinned = sorted(os.sched_getaffinity(0))[:8]
    os.sched_setaffinity(0, pinned)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from fastapi.testclient import TestClient
from app.deterministic_blueprint import BlueprintEngine, Options
from app.deterministic_blueprint.service import app
from app.deterministic_blueprint.calibration import installed_languages


def fixture():
    image = np.full((1600, 2400, 3), 255, np.uint8)
    cv2.rectangle(image, (200, 200), (2200, 1400), (100, 100, 200), 28)
    for x in (800, 1500):
        cv2.line(image, (x, 200), (x, 1400), (100, 100, 200), 24)
    cv2.line(image, (800, 800), (2200, 800), (100, 100, 200), 24)
    cv2.line(image, (2200, 220), (2200, 1380), (140, 75, 30), 28)
    cv2.rectangle(image, (1000, 180), (1150, 220), (255, 255, 255), -1)
    for i, (left, right, value) in enumerate(
        [(200, 2200, 2000), (200, 800, 600), (800, 1500, 700)]
    ):
        y = 40 + i * 55
        cv2.line(image, (left, y), (right, y), (0, 0, 0), 1)
        for x in (left, right):
            cv2.line(image, (x, y - 12), (x, y + 12), (0, 0, 0), 1)
        cv2.putText(
            image,
            str(value),
            ((left + right) // 2 - 35, y - 15),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 0),
            1,
        )
    for x in (300, 950, 1700):
        cv2.rectangle(image, (x, 400), (x + 120, 550), (0, 0, 0), 2)
        cv2.circle(image, (x, 1000), 50, (0, 0, 0), 2)
    return cv2.imencode(".png", image)[1].tobytes()


def summarize(times):
    return {
        "seconds": times,
        "min": min(times),
        "median": statistics.median(times),
        "p95": float(np.percentile(times, 95)),
        "max": max(times),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, action="append", default=[])
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--budget", type=float, default=3.5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    cv2.setNumThreads(8)
    fixtures = [
        ("synthetic_2400x1600", fixture()),
        *[(p.name, p.read_bytes()) for p in args.image],
    ]
    report = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": platform.processor(),
        "cpu_affinity": pinned,
        "effective_cpu_count": len(pinned) if pinned else os.cpu_count(),
        "opencv": cv2.__version__,
        "numpy": np.__version__,
        "tesseract_languages": sorted(installed_languages()),
        "budget_seconds": args.budget,
        "measurement": "in-process warm and HTTP TestClient with a fresh isolated worker per request; includes import/startup/decode/OCR/vectors/PNG/SVG/DXF/ZIP, excludes network transfer and dependency install",
        "cases": [],
    }
    with TestClient(app) as client:
        for name, data in fixtures:
            case = {
                "name": name,
                "source_sha256": hashlib.sha256(data).hexdigest(),
                "source_size_px": list(
                    cv2.imdecode(np.frombuffer(data, np.uint8), 1).shape[1::-1]
                ),
                "results": [],
            }
            for ocr in (False, True):
                options = Options(ocr=ocr, default_scale_px_per_cm=1)
                # Record first direct call separately; then repeated warm calls.
                start = time.perf_counter()
                initial = BlueprintEngine(options).process_bytes(data)
                direct_first = time.perf_counter() - start
                direct = []
                for _ in range(args.runs):
                    start = time.perf_counter()
                    BlueprintEngine(options).process_bytes(data)
                    direct.append(time.perf_counter() - start)
                isolated = []
                failures = []
                stages = []
                for _ in range(args.runs):
                    start = time.perf_counter()
                    response = client.post(
                        "/extract",
                        files={"file": ("plan.png", data, "image/png")},
                        data={"options": options.model_dump_json()},
                    )
                    isolated.append(time.perf_counter() - start)
                    if response.status_code != 200:
                        failures.append(
                            {"status": response.status_code, "body": response.text}
                        )
                    else:
                        with zipfile.ZipFile(BytesIO(response.content)) as archive:
                            stages.append(
                                json.loads(archive.read("report.json"))[
                                    "timings_seconds"
                                ]
                            )
                case["results"].append(
                    {
                        "ocr_enabled": ocr,
                        "first_direct_seconds": direct_first,
                        "warm_pipeline": summarize(direct),
                        "isolated_worker_http": summarize(isolated),
                        "http_failures": failures,
                        "stages_seconds_each_worker": stages,
                        "sample_warnings": initial.report["warnings"],
                        "scale_source": initial.report["calibration"]["source"],
                        "pass": not failures
                        and max([direct_first, *direct, *isolated]) < args.budget,
                    }
                )
                print(
                    f"{name}: OCR={ocr}, first={direct_first:.3f}s, warm max={max(direct):.3f}s, isolated max={max(isolated):.3f}s, failures={len(failures)}",
                    flush=True,
                )
            report["cases"].append(case)
    report["pass"] = all(r["pass"] for c in report["cases"] for r in c["results"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
