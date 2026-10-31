import io, json, zipfile
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
        bp = Blueprint(project_id=p.id, filename="House", local_path=str(path),
                       preview_path=str(path), width=800, height=600)
        s.add(bp)
        s.commit()
        bid = bp.id
    return TestClient(main.app), bid


def plan(**extra):
    pts = [(100, 100), (700, 100), (700, 500), (100, 500)]
    return {
        "id": "x",
        "imageTransform": {"width": 800, "height": 600},
        "nodes": [{"id": f"n{i}", "x": x, "y": y} for i, (x, y) in enumerate(pts)],
        "walls": [{"id": f"w{i}", "a": f"n{i}", "b": f"n{(i + 1) % 4}", "thicknessPx": 10}
                  for i in range(4)],
        **extra,
    }


def reference(length=6):
    return {"reference": {"p1": {"x": 100, "y": 100}, "p2": {"x": 700, "y": 100},
                          "lengthMeters": length}}


def draw_plan(bid):
    import cv2, numpy as np

    with Session(main.engine) as s:
        bp = s.get(Blueprint, bid)
        image = np.full((600, 800, 3), 255, np.uint8)
        cv2.rectangle(image, (100, 100), (700, 500), (100, 100, 200), 15)
        cv2.line(image, (400, 100), (400, 500), (100, 100, 200), 12)
        cv2.imwrite(bp.preview_path, image)


def test_upload_extraction_produces_editable_connected_model(client):
    c, bid = client
    assert c.get(f"/blueprints/{bid}/plan").json() == {"revision": 0, "model": None}
    draw_plan(bid)
    result = c.post(f"/blueprints/{bid}/plan/extract?expected_revision=0")
    assert result.status_code == 200, result.text
    body = result.json()
    model = body["model"]
    assert body["revision"] == 1 and model["revision"] == 1
    assert len(model["walls"]) >= 4 and model["nodes"]
    assert model["scale"]["metersPerPixel"] is None
    assert len(model["rooms"]) == 2
    assert all(o["hostWallId"] or o["status"] == "proposed" for o in model["openings"])
    assert c.post(f"/blueprints/{bid}/plan/extract?expected_revision=0").status_code == 409


def test_save_revisions_conflicts_and_validation(client):
    c, bid = client
    path = f"/blueprints/{bid}/plan"
    first = c.put(path, json={"expectedRevision": 0, "model": plan()})
    assert first.status_code == 200, first.text
    assert first.json()["model"]["rooms"][0]["areaPx2"] == pytest.approx(590 * 390)
    assert c.put(path, json={"expectedRevision": 0, "model": plan()}).status_code == 409
    bad = plan()
    bad["imageTransform"]["width"] = 900
    assert c.put(path, json={"expectedRevision": 1, "model": bad}).status_code == 422
    assert len(c.get(path + "/history").json()) == 1


def test_measurement_only_changes_scale(client):
    c, bid = client
    path = f"/blueprints/{bid}/plan"
    a = c.put(path, json={"expectedRevision": 0, "model": plan()}).json()["model"]
    b = c.put(path, json={"expectedRevision": 1,
                          "model": {**a, "scale": reference(2.9)}}).json()["model"]
    assert b["scale"]["metersPerPixel"] == pytest.approx(2.9 / 600)
    for key in ("nodes", "walls", "openings", "rooms"):
        assert a[key] == b[key]


def test_export_requires_scale_and_decided_openings(client):
    c, bid = client
    path = f"/blueprints/{bid}/plan"
    proposed = [{"id": "o", "kind": "window", "hostWallId": "w0", "offsetPx": 100,
                 "widthPx": 100, "heightM": 1.2, "sillM": 0.9, "status": "proposed",
                 "confidence": 0.5}]
    c.put(path, json={"expectedRevision": 0, "model": plan(openings=proposed)})
    assert c.get(path + "/export").status_code == 422
    c.put(path, json={"expectedRevision": 1,
                      "model": plan(openings=proposed, scale=reference())})
    blocked = c.get(path + "/export")
    assert blocked.status_code == 422 and "Approve" in blocked.text
    proposed[0]["status"] = "confirmed"
    c.put(path, json={"expectedRevision": 2,
                      "model": plan(openings=proposed, scale=reference())})
    archive = c.get(path + "/export")
    assert archive.status_code == 200, archive.text
    files = zipfile.ZipFile(io.BytesIO(archive.content))
    assert "walls.dxf" in files.namelist()
    assert json.loads(files.read("report.json"))["revision"] == 3


def test_straightening_creates_new_plan_and_preserves_reference(client, tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "storage_path", str(tmp_path / "storage"))
    c, bid = client
    model = plan(scale={"reference": {"p1": {"x": 200, "y": 200}, "p2": {"x": 500, "y": 200},
                                      "lengthMeters": 3}})
    assert c.put(f"/blueprints/{bid}/plan",
                 json={"expectedRevision": 0, "model": model}).status_code == 200
    corners = [[70, 40], [740, 80], [700, 550], [50, 520]]
    result = c.post(f"/blueprints/{bid}/plan/straighten",
                    json={"expectedRevision": 1, "corners": corners,
                          "pageAspectRatio": 1.41421356})
    assert result.status_code == 200, result.text
    target = result.json()["id"]
    assert target != bid and result.json()["referencePreserved"]
    assert c.get(f"/blueprints/{bid}/plan").json()["model"]["walls"]
    moved = c.get(f"/blueprints/{target}/plan").json()["model"]
    assert moved["scale"]["reference"]["lengthMeters"] == 3 and moved["walls"] == []
    stale = c.post(f"/blueprints/{bid}/plan/straighten",
                   json={"expectedRevision": 0, "corners": corners, "pageAspectRatio": 1.4})
    assert stale.status_code == 409


def test_unavailable_configured_model_reports_runtime_problem_and_keeps_saved_plan(
    client, tmp_path, monkeypatch
):
    from app.config import settings

    c, bid = client
    path = f"/blueprints/{bid}/plan"
    saved = c.put(path, json={"expectedRevision": 0, "model": plan()}).json()
    monkeypatch.setattr(settings, "workspace_semantic_source", str(tmp_path))
    monkeypatch.setattr(settings, "workspace_semantic_weights", str(tmp_path / "missing.pkl"))
    monkeypatch.setenv("WORKSPACE_SEMANTIC_SOURCE", str(tmp_path))
    monkeypatch.setenv("WORKSPACE_SEMANTIC_WEIGHTS", str(tmp_path / "missing.pkl"))
    result = c.post(path + "/extract?expected_revision=1")
    assert result.status_code == 503
    assert "configuration" in result.json()["detail"]
    assert c.get(path).json() == {"revision": 1, "model": saved["model"]}


def test_invalid_outline_does_not_run_extraction_or_replace_saved_model(client,monkeypatch):
    from app import plan_api
    c,bid=client
    route=f'/blueprints/{bid}/plan'
    before=c.put(route,json={'expectedRevision':0,'model':plan()}).json()
    async def forbidden(*args,**kwargs):
        raise AssertionError('invalid outline reached extraction')
    monkeypatch.setattr(plan_api,'run_worker',forbidden)
    for outline in [[{'x':-10,'y':100},{'x':700,'y':100},{'x':700,'y':500}],
                    [{'x':100,'y':100},{'x':700,'y':500},{'x':100,'y':500},{'x':700,'y':100}]]:
        result=c.post(route+'/extract?expected_revision=1',json={'envelope':outline})
        assert result.status_code==422
    assert c.get(route).json()==before


def test_invalid_approval_profile_keeps_saved_revision_and_skips_worker(client,tmp_path,monkeypatch):
    from app.config import settings
    from app import plan_api
    c,bid=client;route=f'/blueprints/{bid}/plan'
    before=c.put(route,json={'expectedRevision':0,'model':plan()}).json()
    monkeypatch.setattr(settings,'opening_confidence_profile',str(tmp_path/'missing.json'))
    async def forbidden(*args,**kwargs):raise AssertionError('invalid configuration reached worker')
    monkeypatch.setattr(plan_api,'run_worker',forbidden)
    result=c.post(route+'/extract?expected_revision=1')
    assert result.status_code==503
    assert c.get(route).json()==before
