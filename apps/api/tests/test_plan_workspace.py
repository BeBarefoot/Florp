import io, zipfile
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine
from app import main
from app.models import Project, Blueprint
from PIL import Image


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main, "engine", engine)
    with Session(engine) as s:
        p = Project(title="House")
        s.add(p)
        s.flush()
        path = tmp_path / "plan.png"
        Image.new("RGB", (800, 600), "white").save(path)
        bp = Blueprint(
            project_id=p.id,
            filename="House",
            local_path=str(path),
            preview_path=str(path),
            width=800,
            height=600,
        )
        s.add(bp)
        s.commit()
        bid = bp.id
    return TestClient(main.app), bid


def document():
    return {
        "width": 800,
        "height": 600,
        "objects": [
            {
                "id": str(i),
                "start": {"x": a[0], "y": a[1]},
                "end": {"x": b[0], "y": b[1]},
                "thickness_px": 10,
            }
            for i, (a, b) in enumerate(
                zip(
                    [(100, 100), (700, 100), (700, 500), (100, 500)],
                    [(700, 100), (700, 500), (100, 500), (100, 100)],
                )
            )
        ],
    }


def test_pixel_document_scale_revision_and_export(client):
    c, bid = client
    path = f"/blueprints/{bid}/workspace"
    assert c.get(path).json()["version"] == 0
    d = document()
    r = c.put(path, json={"expected_version": 0, "document": d})
    assert r.status_code == 200, r.text
    assert r.json()["derived"]["px_per_meter"] is None
    assert c.get(path + "/export").status_code == 422
    d["reference"] = {"start": [100, 100], "end": [700, 100], "length_cm": 600}
    r = c.put(path, json={"expected_version": 1, "document": d})
    assert r.status_code == 200
    assert r.json()["derived"]["px_per_meter"] == 100
    room = r.json()["derived"]["rooms"][0]
    assert room["area_m2"] == pytest.approx(5.9 * 3.9)
    assert c.put(path, json={"expected_version": 1, "document": d}).status_code == 409
    archive = c.get(path + "/export")
    assert archive.status_code == 200
    assert "walls.dxf" in zipfile.ZipFile(io.BytesIO(archive.content)).namelist()
    assert c.get(path).json()["document"]["reference"] == d["reference"]


def test_invalid_host_reference_and_dimensions(client):
    c, bid = client
    path = f"/blueprints/{bid}/workspace"
    d = document()
    d["reference"] = {"start": [10, 10], "end": [11, 10], "length_cm": 100}
    assert c.put(path, json={"expected_version": 0, "document": d}).status_code == 422
    d = document()
    d["objects"][0]["host_id"] = "missing"
    assert c.put(path, json={"expected_version": 0, "document": d}).status_code == 422
    d = document()
    d["width"] = 900
    assert c.put(path, json={"expected_version": 0, "document": d}).status_code == 422


def test_extraction_without_reference_is_a_proposal_and_does_not_overwrite(client):
    c, bid = client
    from app import main
    from sqlmodel import Session
    from app.models import Blueprint
    import cv2, numpy as np

    with Session(main.engine) as s:
        bp = s.get(Blueprint, bid)
        image = np.full((600, 800, 3), 255, np.uint8)
        cv2.rectangle(image, (100, 100), (700, 500), (100, 100, 200), 15)
        cv2.imwrite(bp.preview_path, image)
    proposal = c.post(f"/blueprints/{bid}/workspace/extract")
    assert proposal.status_code == 200, proposal.text
    assert proposal.json()["document"]["objects"]
    assert proposal.json()["document"]["reference"] is None
    assert c.get(f"/blueprints/{bid}/workspace").json()["version"] == 0
    saved = c.put(
        f"/blueprints/{bid}/workspace",
        json={"expected_version": 0, "document": proposal.json()["document"]},
    )
    assert saved.status_code == 200
    assert (
        c.post(f"/blueprints/{bid}/workspace/extract?expected_version=0").status_code
        == 409
    )
    assert len(c.get(f"/blueprints/{bid}/workspace/history").json()) == 1


def test_cv_window_proposal_uses_supported_rails_and_host():
    import cv2, numpy as np
    from app.cv_openings import propose
    from app.plan_workspace import Segment, Point

    image = np.full((200, 400, 3), 255, np.uint8)
    walls = [
        Segment(id="a", start=Point(x=50, y=100), end=Point(x=150, y=100)),
        Segment(id="b", start=Point(x=210, y=100), end=Point(x=350, y=100)),
    ]
    assert not propose(image, walls)
    for y in (97, 103):
        cv2.line(image, (150, y), (210, y), (0, 0, 0), 1)
    result = propose(image, walls)
    assert len(result) == 2
    assert result[1].kind == "window" and result[1].host_id == result[0].id
    assert result[1].uncertain


def test_recalibration_scales_metrics_without_moving_objects(client):
    c, bid = client
    path = f"/blueprints/{bid}/workspace"
    d = document()
    d["reference"] = {"start": [100, 100], "end": [700, 100], "length_cm": 600}
    a = c.put(path, json={"expected_version": 0, "document": d}).json()
    d["reference"]["length_cm"] = 1200
    b = c.put(path, json={"expected_version": 1, "document": d}).json()
    assert a["document"]["objects"] == b["document"]["objects"]
    assert b["derived"]["rooms"][0]["area_m2"] == pytest.approx(
        a["derived"]["rooms"][0]["area_m2"] * 4
    )
    assert b["derived"]["margin_px"] == 25
    import json

    archive = c.get(path + "/export")
    report = json.loads(
        zipfile.ZipFile(io.BytesIO(archive.content)).read("report.json")
    )
    assert report["margin_cm"] == 50


def test_opening_height_and_source_alignment_guard(client):
    c, bid = client
    d = document()
    d["objects"].append(
        {
            "id": "window",
            "kind": "window",
            "start": {"x": 200, "y": 100},
            "end": {"x": 300, "y": 100},
            "host_id": "0",
            "height_m": 1.2,
            "sill_m": 0.9,
        }
    )
    path = f"/blueprints/{bid}/workspace"
    assert c.put(path, json={"expected_version": 0, "document": d}).status_code == 200
    d["objects"][-1]["sill_m"] = 2
    assert c.put(path, json={"expected_version": 1, "document": d}).status_code == 422


def test_straightening_creates_new_plan_preserves_source_and_reference(
    client, tmp_path, monkeypatch
):
    from app.config import settings

    monkeypatch.setattr(settings, "storage_path", str(tmp_path / "storage"))
    c, bid = client
    d = document()
    d["reference"] = {"start": [200, 200], "end": [500, 200], "length_cm": 300}
    saved = c.put(
        f"/blueprints/{bid}/workspace", json={"expected_version": 0, "document": d}
    )
    assert saved.status_code == 200
    result = c.post(
        f"/blueprints/{bid}/workspace/straighten",
        json={
            "expected_version": 1,
            "corners": [[70, 40], [740, 80], [700, 550], [50, 520]],
            "page_aspect_ratio": 1.41421356,
        },
    )
    assert result.status_code == 200, result.text
    target = result.json()["id"]
    assert target != bid and result.json()["reference_preserved"]
    original = c.get(f"/blueprints/{bid}/workspace").json()
    assert original["version"] == 1 and original["document"]["objects"]
    normalized = c.get(f"/blueprints/{target}/workspace").json()
    assert normalized["document"]["reference"]["length_cm"] == 300
    assert normalized["document"]["objects"] == []
    assert (
        c.post(
            f"/blueprints/{bid}/workspace/straighten",
            json={
                "expected_version": 0,
                "corners": [[70, 40], [740, 80], [700, 550], [50, 520]],
                "page_aspect_ratio": 1.414,
            },
        ).status_code
        == 409
    )


def test_isolated_diagonal_evidence_is_retained(tmp_path):
    import cv2, numpy as np
    from app.workspace_worker import build

    image = np.full((400, 500, 3), 255, np.uint8)
    cv2.line(image, (70, 70), (350, 320), (100, 100, 200), 12)
    file = tmp_path / "diagonal.png"
    cv2.imwrite(str(file), image)
    doc = build(file)
    assert any(
        o.id.startswith("diagonal-")
        and abs(o.end.x - o.start.x) > 100
        and abs(o.end.y - o.start.y) > 100
        for o in doc.objects
    )
