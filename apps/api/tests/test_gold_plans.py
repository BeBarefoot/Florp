"""Ratcheting regression on user-corrected gold plans (data/gold/<name>/).

Skipped when no gold data exists. thresholds.json holds minimums that are only
ever raised; write them with ``python scripts/evaluate_workspace.py --gold <name> --update-thresholds``.
"""

import pytest
from app.extraction_coverage import GOLD, case_directories, score_case, threshold_violations
from app.opening_calibration import load_gold

CASES = case_directories(GOLD)

pytestmark = pytest.mark.skipif(not CASES, reason="no gold plans in data/gold")


@pytest.mark.parametrize("case", CASES, ids=lambda p: p.name)
def test_gold_case(case):
    source, reference, _ = load_gold(case)
    violations = threshold_violations(case, score_case(source, reference))
    assert not violations, violations
