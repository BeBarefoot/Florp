"""Create, but never activate, an opening approval profile from reviewed gold cases.

uv run python scripts/calibrate_openings.py --gold-root data/gold --output data/opening-confidence.json
"""

from __future__ import annotations
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.opening_calibration import load_gold, tune
from app.plan_reconstruct import reconstruct, ReconstructConfig
from app.plan_score import opening_observations
from app.workspace_worker import build


def calibrate(root, min_precision=0.95, min_examples=10):
    cases = sorted(p for p in Path(root).glob("*") if (p / "gold.json").exists())
    if len(cases) < 3:
        raise ValueError("Supply at least three reviewed reference cases")
    records = [load_gold(case) for case in cases]
    hashes = [identity for _, _, identity in records]
    if len(set(hashes)) != len(hashes):
        raise ValueError("Duplicate source images cannot count as independent cases")
    observations = {"door": [], "window": []}
    for source, gold, _ in records:
        predicted = reconstruct(
            build(source), gold.id, ReconstructConfig(auto_confirm=1.01)
        )
        for kind, samples in opening_observations(predicted, gold).items():
            observations[kind].extend(samples)
    return tune(observations, hashes, min_precision, min_examples)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--gold-root", type=Path, default=Path("data/gold"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-precision", type=float, default=0.95)
    parser.add_argument("--min-examples", type=int, default=10)
    args = parser.parse_args()
    try:
        profile = calibrate(args.gold_root, args.min_precision, args.min_examples)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(profile.model_dump_json(indent=2))
    print(
        json.dumps(
            {
                "profile": str(args.output),
                "thresholds": profile.thresholds,
                "active": False,
                "note": "Empirical precision on these cases is not a guarantee on unseen plans.",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
