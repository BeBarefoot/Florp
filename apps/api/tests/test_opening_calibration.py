import json
import pytest
from app.opening_calibration import tune, load_profile, load_gold, Profile
from app.plan_model import PlanModel, Opening, Pt
from app.plan_score import score, opening_observations
from test_plan_model import square

HASHES = ["a" * 64, "b" * 64, "c" * 64]


def test_calibration_requires_precision_and_support_instead_of_promoting_everything():
    samples = {
        "door": [(0.75, False), (0.8, False), (0.91, True), (0.95, True), (0.97, True)],
        "window": [(0.9, True)],
    }
    profile = tune(samples, HASHES, min_precision=0.95, min_examples=3)
    assert profile.thresholds == {"door": 0.91, "window": 1.01}
    assert profile.sample_counts["door"] == 3
    assert profile.empirical_precision["door"] == 1


def test_profiles_reject_unknown_kinds_nan_and_duplicate_sources():
    raw = tune({}, HASHES).model_dump()
    raw["thresholds"]["garage"] = 0.5
    with pytest.raises(ValueError):
        Profile.model_validate(raw)
    raw = tune({}, HASHES).model_dump()
    raw["thresholds"]["door"] = float("nan")
    with pytest.raises(ValueError):
        Profile.model_validate(raw)
    with pytest.raises(ValueError):
        tune({}, [HASHES[0], HASHES[0]])


def test_configured_profile_applies_but_cannot_auto_confirm_garage(
    tmp_path, monkeypatch
):
    from app.config import settings
    from app.plan_reconstruct import reconstruct
    from app.plan_workspace import Document, Segment, Point

    profile = tune({"door": [(0.75, True)] * 3, "window": []}, HASHES, min_examples=3)
    path = tmp_path / "profile.json"
    path.write_text(profile.model_dump_json())
    monkeypatch.setattr(settings, "opening_confidence_profile", str(path))
    wall = Segment(id="w", start=Point(x=20, y=50), end=Point(x=600, y=50))

    def opening(id, kind, x):
        return Segment(
            id=id,
            kind=kind,
            start=Point(x=x, y=50),
            end=Point(x=x + 60, y=50),
            confidence=0.8,
            height_m=2.1,
        )

    result = reconstruct(
        Document(
            width=640,
            height=400,
            objects=[wall, opening("d", "door", 100), opening("g", "garage", 300)],
        ),
        "case",
    )
    assert next(o for o in result.openings if o.kind == "door").status == "confirmed"
    assert next(o for o in result.openings if o.kind == "garage").status == "proposed"


def test_orphan_prediction_counts_as_false_positive():
    gold = PlanModel.model_validate(square(openings=[]))
    pred = gold.model_copy(deep=True)
    pred.openings.append(
        Opening(
            id="orphan",
            kind="door",
            span=(Pt(x=300, y=300), Pt(x=350, y=300)),
            confidence=0.99,
        )
    )
    result = score(pred, gold)
    assert result["openings"]["door"]["predicted"] == 1
    assert result["openings"]["door"]["precision"] == 0
    assert opening_observations(pred, gold)["door"] == [(0.99, False)]


def test_thick_prediction_does_not_relax_its_own_precision_tolerance():
    gold = PlanModel.model_validate(square())
    pred = gold.model_copy(deep=True)
    for node in pred.nodes:
        node.x += 35
    for wall in pred.walls:
        wall.thickness_px = 500
    assert score(pred, gold)["wall_precision"] < 0.8


def test_snapshot_keeps_source_identity_goals_and_archived_revisions(tmp_path):
    from PIL import Image
    from scripts.snapshot_gold import write_snapshot

    image = tmp_path / "source.png"
    Image.new("RGB", (800, 600), "white").save(image)
    raw = square()
    raw["imageTransform"] = {"width": 800, "height": 600}
    out = write_snapshot(image, raw, tmp_path / "gold", "case1")
    assert load_gold(out)[2] in (out / "metadata.json").read_text()
    assert json.loads((out / "thresholds.json").read_text())["garage_f1"] == 0.8
    with pytest.raises(ValueError, match="Snapshot exists"):
        write_snapshot(image, raw, tmp_path / "gold", "case1")
    write_snapshot(image, raw, tmp_path / "gold", "case1", replace=True)
    assert len(list((tmp_path / "gold/.history").iterdir())) == 1
    Image.new("RGB", (800, 600), "black").save(out / "preview.png")
    with pytest.raises(ValueError, match="hash"):
        load_gold(out)


def test_snapshot_rejects_path_escape_and_unreviewed_opening(tmp_path):
    from PIL import Image
    from scripts.snapshot_gold import write_snapshot

    image = tmp_path / "source.png"
    Image.new("RGB", (800, 600), "white").save(image)
    with pytest.raises(ValueError, match="simple case name"):
        write_snapshot(image, square(), tmp_path / "gold", "../escape")
    raw = square(
        openings=[
            {
                "id": "o",
                "kind": "window",
                "hostWallId": "w0",
                "offsetPx": 20,
                "widthPx": 40,
                "status": "proposed",
            }
        ]
    )
    with pytest.raises(ValueError, match="reviewing"):
        write_snapshot(image, raw, tmp_path / "gold", "case1")


def test_gold_minimums_cannot_be_silently_disabled():
    from app.plan_score import minimum_thresholds

    assert minimum_thresholds({})["wall_recall"] == 0.9
    assert minimum_thresholds({"wall_recall": 0.1})["wall_recall"] == 0.9
    assert minimum_thresholds({"wall_recall": 0.95})["wall_recall"] == 0.95
    with pytest.raises(ValueError):
        minimum_thresholds({"misspelled_metric": 0.9})


def test_calibration_without_reference_cases_does_not_invent_a_profile(tmp_path):
    from scripts.calibrate_openings import calibrate

    with pytest.raises(ValueError, match="three reviewed"):
        calibrate(tmp_path)


def test_active_threshold_without_support_is_rejected():
    raw = tune({}, HASHES).model_dump()
    raw["thresholds"]["door"] = 0.8
    with pytest.raises(ValueError, match="lacks supporting"):
        Profile.model_validate(raw)
