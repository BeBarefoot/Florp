import pytest
from pydantic import ValidationError
from app.plan_model import PlanModel


def square(**extra):
    pts = [(100, 100), (700, 100), (700, 500), (100, 500)]
    return {
        "id": "plan",
        "imageTransform": {"width": 800, "height": 600},
        "nodes": [{"id": f"n{i}", "x": x, "y": y} for i, (x, y) in enumerate(pts)],
        "walls": [
            {"id": f"w{i}", "a": f"n{i}", "b": f"n{(i + 1) % 4}", "thicknessPx": 10}
            for i in range(4)
        ],
        **extra,
    }


def test_camel_case_round_trip_matches_frontend_contract():
    model = PlanModel.model_validate(square())
    data = model.dump()
    assert data["schemaVersion"] == 2
    assert data["walls"][0]["thicknessPx"] == 10
    assert data["scale"] == {"metersPerPixel": None, "reference": None}


def test_rejects_dangling_node_reference_and_degenerate_wall():
    data = square()
    data["walls"][0]["b"] = "missing"
    with pytest.raises(ValidationError):
        PlanModel.model_validate(data)
    data = square()
    data["walls"][0]["b"] = "n0"
    with pytest.raises(ValidationError):
        PlanModel.model_validate(data)


def test_rejects_opening_that_overruns_its_host_or_height():
    data = square(
        openings=[
            {"id": "o", "kind": "door", "hostWallId": "w0", "offsetPx": 550,
             "widthPx": 100, "heightM": 2.1, "status": "confirmed"}
        ]
    )
    with pytest.raises(ValidationError):
        PlanModel.model_validate(data)
    data["openings"][0].update(offsetPx=100, heightM=3.5)
    with pytest.raises(ValidationError):
        PlanModel.model_validate(data)


def test_confirmed_opening_requires_host_but_proposal_may_float():
    span = [{"x": 200, "y": 300}, {"x": 260, "y": 300}]
    data = square(openings=[{"id": "o", "kind": "window", "span": span, "status": "confirmed"}])
    with pytest.raises(ValidationError):
        PlanModel.model_validate(data)
    data["openings"][0]["status"] = "proposed"
    assert PlanModel.model_validate(data).openings[0].host_wall_id is None


def test_single_measurement_sets_scale_without_touching_pixels():
    plain = PlanModel.model_validate(square())
    data = square(scale={"reference": {"p1": {"x": 100, "y": 100},
                                        "p2": {"x": 200, "y": 100},
                                        "lengthMeters": 2.9}})
    calibrated = PlanModel.model_validate(data)
    assert calibrated.scale.meters_per_pixel == pytest.approx(0.029)
    assert calibrated.dump()["nodes"] == plain.dump()["nodes"]
    assert calibrated.dump()["walls"] == plain.dump()["walls"]


def test_client_supplied_scale_is_recomputed_not_trusted():
    data = square(scale={"metersPerPixel": 5,
                         "reference": {"p1": {"x": 100, "y": 100},
                                       "p2": {"x": 200, "y": 100},
                                       "lengthMeters": 1}})
    assert PlanModel.model_validate(data).scale.meters_per_pixel == pytest.approx(0.01)
    data["scale"]["reference"]["p2"] = {"x": 102, "y": 100}
    with pytest.raises(ValidationError):
        PlanModel.model_validate(data)
