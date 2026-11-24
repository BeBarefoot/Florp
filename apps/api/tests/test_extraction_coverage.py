from app import extraction_coverage


def test_empty_coverage_distinguishes_regression_and_held_out(tmp_path):
    report = extraction_coverage.coverage(tmp_path / "missing")
    assert report["corrected_plan_regressions"]["cases_scored"] == 0
    assert report["held_out_release"] == {"status": "not_configured", "case_count": 0}


def test_coverage_counts_incomplete_failed_and_scored_cases(tmp_path, monkeypatch):
    def load(case):
        if case.name == "invalid":
            raise ValueError("Source hash mismatch")
        return case / "preview.png", object(), "same-source"

    monkeypatch.setattr(extraction_coverage, "load_gold", load)
    monkeypatch.setattr(extraction_coverage, "score_case", lambda source, reference: {})
    monkeypatch.setattr(extraction_coverage, "threshold_violations", lambda case, result:
                        {"wall_recall": {"actual": .5, "minimum": .9}} if case.name == "below" else {})
    for name in ("incomplete", "invalid", "passed", "below"):
        case = tmp_path / name
        case.mkdir()
        (case / "gold.json").touch()
        if name != "incomplete":
            (case / "preview.png").touch()
    regression = extraction_coverage.coverage(tmp_path)["corrected_plan_regressions"]
    assert regression["cases_discovered"] == 4
    assert regression["cases_scored"] == 2
    assert regression["distinct_scored_sources"] == 1
    assert [regression[key] for key in ("unavailable", "error", "below_threshold", "passed")] == [1, 1, 1, 1]
