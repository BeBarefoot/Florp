"""Ratcheting regression on user-corrected gold plans (data/gold/<name>/).

Skipped when no gold data exists. thresholds.json holds minimums that are only
ever raised; write them with ``python scripts/evaluate_workspace.py --gold <name> --update-thresholds``.
"""

import json
from pathlib import Path
import pytest

GOLD = Path(__file__).resolve().parents[1] / "data" / "gold"
CASES = (
    sorted(p for p in GOLD.glob("*") if (p / "gold.json").exists())
    if GOLD.exists()
    else []
)

pytestmark = pytest.mark.skipif(not CASES, reason="no gold plans in data/gold")


def run_case(case: Path):
    from app.plan_model import PlanModel
    from app.plan_reconstruct import reconstruct
    from app.plan_score import score
    from app.workspace_worker import build

    gold = PlanModel.model_validate(json.loads((case / "gold.json").read_text()))
    predicted = reconstruct(build(case / "preview.png"), gold.id)
    return score(predicted, gold)


def metrics(result):
    from app.plan_score import flat_metrics

    return flat_metrics(result)


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_gold_case(case):
    from app.plan_score import minimum_thresholds

    thresholds = minimum_thresholds(
        json.loads((case / "thresholds.json").read_text())
        if (case / "thresholds.json").exists()
        else {}
    )
    got = metrics(run_case(case))
    for key, minimum in thresholds.items():
        assert (
            got[key] >= minimum - 1e-9
        ), f"{case.name}: {key} {got[key]:.3f} < {minimum:.3f}"
