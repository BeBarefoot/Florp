import pytest
from app.plan_model import PlanModel
from app.plan_derive import derive, FINDING_CAP


def two_rooms(t=10):
    pts = [(100, 100), (250, 100), (400, 100), (400, 300), (250, 300), (100, 300)]
    walls = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 0), (1, 4)]
    return {
        "id": "p",
        "imageTransform": {"width": 800, "height": 600},
        "nodes": [{"id": f"n{i}", "x": x, "y": y} for i, (x, y) in enumerate(pts)],
        "walls": [{"id": f"w{i}", "a": f"n{a}", "b": f"n{b}", "thicknessPx": t}
                  for i, (a, b) in enumerate(walls)],
    }


def test_rooms_use_inner_wall_faces():
    model = derive(PlanModel.model_validate(two_rooms()))
    assert len(model.rooms) == 2
    for room in model.rooms:
        assert room.area_px2 == pytest.approx((150 - 10) * (200 - 10), rel=0.01)


def test_room_labels_survive_node_edits():
    model = derive(PlanModel.model_validate(two_rooms()))
    model.rooms[0].label = "Bedroom"
    data = model.dump()
    data["nodes"][0]["x"] = 90
    edited = derive(PlanModel.model_validate(data))
    assert sorted(r.label or "" for r in edited.rooms) == ["", "Bedroom"]


def test_dangling_findings_are_clustered_and_capped():
    data = two_rooms()
    for i in range(60):
        data["nodes"].append({"id": f"s{i}a", "x": 500 + i * 0.5, "y": 400})
        data["nodes"].append({"id": f"s{i}b", "x": 500 + i * 0.5, "y": 450})
        data["walls"].append({"id": f"s{i}", "a": f"s{i}a", "b": f"s{i}b", "thicknessPx": 10})
    model = derive(PlanModel.model_validate(data))
    ends = [f for f in model.findings if f.category == "open_wall_end"]
    assert len(ends) <= 2 and sum(f.count for f in ends) == 120

    for i in range(200):
        x = 20 + (i % 20) * 38
        y = 320 + (i // 20) * 27
        data["nodes"] += [{"id": f"z{i}a", "x": x, "y": y}, {"id": f"z{i}b", "x": x + 5, "y": y}]
        data["walls"].append({"id": f"z{i}", "a": f"z{i}a", "b": f"z{i}b", "thicknessPx": 1})
    model = derive(PlanModel.model_validate(data))
    assert len([f for f in model.findings if f.category == "open_wall_end"]) <= FINDING_CAP


def test_proposed_openings_each_get_an_approval_finding_and_cannot_be_dismissed():
    data = two_rooms()
    data["openings"] = [
        {"id": f"o{i}", "kind": "window", "hostWallId": "w0", "offsetPx": 10 + i * 30,
         "widthPx": 20, "heightM": 1.2, "sillM": 0.9, "status": "proposed", "confidence": 0.5}
        for i in range(4)
    ]
    data["dismissedFindings"] = ["opening_needs_approval:o0"]
    model = derive(PlanModel.model_validate(data))
    approvals = [f for f in model.findings if f.category == "opening_needs_approval"]
    assert len(approvals) == 4
    data["openings"][0]["status"] = "confirmed"
    model = derive(PlanModel.model_validate(data))
    assert len([f for f in model.findings if f.category == "opening_needs_approval"]) == 3


def test_dismissed_findings_stay_hidden():
    data = two_rooms()
    data["nodes"].append({"id": "x", "x": 600, "y": 400})
    data["walls"].append({"id": "stub", "a": "n3", "b": "x", "thicknessPx": 10})
    model = derive(PlanModel.model_validate(data))
    finding = next(f for f in model.findings if f.category == "open_wall_end")
    data["dismissedFindings"] = [finding.id]
    assert not [f for f in derive(PlanModel.model_validate(data)).findings
                if f.category == "open_wall_end"]
