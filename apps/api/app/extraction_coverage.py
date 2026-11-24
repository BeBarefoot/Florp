"""Report local real-plan regressions separately from held-out release evaluation."""

import argparse
import json
import time
from pathlib import Path

from .opening_calibration import load_gold
from .plan_score import flat_metrics, minimum_thresholds, score

GOLD = Path(__file__).resolve().parents[1] / "data" / "gold"


def case_directories(root):
    return sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")) if root.is_dir() else []


def score_case(source, reference):
    from .plan_reconstruct import reconstruct
    from .workspace_worker import build

    return score(reconstruct(build(source), reference.id), reference)


def threshold_violations(case, result):
    path = case / "thresholds.json"
    thresholds = minimum_thresholds(json.loads(path.read_text()) if path.exists() else {})
    metrics = flat_metrics(result)
    return {
        name: {"actual": metrics[name], "minimum": minimum}
        for name, minimum in thresholds.items() if metrics[name] < minimum - 1e-9
    }


def coverage(root, release_manifest=None):
    cases = []
    regression_sources = set()
    scored_sources = set()
    for case in case_directories(root):
        entry = {"case": case.name}
        missing = [name for name in ("preview.png", "gold.json") if not (case / name).is_file()]
        if missing:
            entry.update(status="unavailable", missing=missing)
        else:
            started = time.perf_counter()
            try:
                source, reference, source_hash = load_gold(case)
                regression_sources.add(source_hash)
                result = score_case(source, reference)
                failures = threshold_violations(case, result)
                scored_sources.add(source_hash)
                entry.update(status="below_threshold" if failures else "passed",
                             metrics=result, threshold_violations=failures)
            except Exception as error:
                entry.update(status="error", error=str(error))
            entry["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        cases.append(entry)

    counts = {status: sum(case["status"] == status for case in cases)
              for status in ("unavailable", "error", "below_threshold", "passed")}
    scored = counts["passed"] + counts["below_threshold"]
    regression = {"cases_discovered": len(cases), "cases_scored": scored,
                  "distinct_scored_sources": len(scored_sources), **counts, "cases": cases}
    release = {"status": "not_configured", "case_count": 0}
    if release_manifest is not None:
        from scripts.evaluate_release import evaluate

        try:
            result = evaluate(release_manifest, excluded_sources=regression_sources)
            release = {"status": "passed" if result["passed"] else "below_threshold", **result}
        except Exception as error:
            release = {"status": "error", "case_count": 0, "error": str(error)}
    return {"corrected_plan_regressions": regression, "held_out_release": release}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-root", type=Path, default=GOLD, help="Private corrected-plan snapshots")
    parser.add_argument("--release-manifest", type=Path, help="Frozen independently reviewed corpus")
    parser.add_argument("--output", type=Path, help="Private per-case JSON report")
    args = parser.parse_args()
    report = coverage(args.gold_root, args.release_manifest)
    regression = report["corrected_plan_regressions"]
    held_out = report["held_out_release"]
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Real-plan regressions scored: {regression['cases_scored']} / {regression['cases_discovered']} cases "
          f"({regression['distinct_scored_sources']} distinct sources).")
    print(f"Regressions passed: {regression['passed']}. Below threshold: {regression['below_threshold']}. "
          f"Unavailable: {regression['unavailable']}. Errors: {regression['error']}.")
    if not regression["cases_scored"]:
        print("No corrected real plans were scored. This run provides no real-plan regression results.")
    print(f"Held-out release: {held_out['status'].replace('_', ' ')} ({held_out['case_count']} cases).")
    if not held_out["case_count"]:
        print("No held-out accuracy evidence from this run.")
    if regression["below_threshold"] or regression["unavailable"] or regression["error"] or (
        args.release_manifest and held_out["status"] != "passed"
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
