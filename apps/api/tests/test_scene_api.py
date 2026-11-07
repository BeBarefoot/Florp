import base64
import io

from PIL import Image

from app import providers
from app.config import settings
from test_plan_api import client, plan, reference  # noqa: F401


def test_scene_render_is_revisioned_and_does_not_resubmit(client, monkeypatch, tmp_path):
    c, bid = client
    path = f"/blueprints/{bid}"
    monkeypatch.setattr(settings, "image_api_key", "mock")
    monkeypatch.setattr(settings, "storage_path", str(tmp_path))
    calls = []

    async def generate(depth, prompt, *, model):
        image = Image.open(io.BytesIO(depth))
        assert image.mode == "L" and image.size == (1024, 768)
        assert image.getpixel((0, 0)) > image.getpixel((1, 0))
        calls.append(prompt)
        return "mock-job", "https://queue.fal.run/status", "https://queue.fal.run/result"

    monkeypatch.setattr(providers, "generate_image", generate)
    initial = c.put(path + "/plan", json={"expectedRevision": 0, "model": plan(scale=reference())})
    assert initial.status_code == 200, initial.text
    config = {"views": [{"id": "bedroom", "name": "Bedroom", "position": {"x": 160, "y": 200},
                         "yaw": 90, "pitch": -10, "horizontalFov": 90, "eyeHeight": 1.6}],
              "objects": [{"id": "bed", "kind": "bed", "position": {"x": 300, "y": 200},
                           "rotation": 0, "width": 1.9, "depth": 2.12, "height": .9,
                           "mattressWidth": 1.8, "mattressDepth": 2}], "style": "Oak"}
    scene = c.put(path + "/scene", json={"expectedRevision": 0, "planRevision": 1, "config": config})
    assert scene.status_code == 200, scene.text
    assert c.get(path + "/scene").json() == scene.json()
    assert c.put(path + "/scene", json={"expectedRevision": 0, "planRevision": 1, "config": config}).status_code == 409

    image = Image.new("RGB", (1024, 768), (0, 7, 208))
    image.putpixel((0, 0), (0, 3, 232))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    png = base64.b64encode(buf.getvalue()).decode()
    payload = {"requestKey": "first", "sceneRevision": 1, "viewId": "bedroom", "name": "Oak",
               "prompt": "Keep visible objects fixed.", "depth": png, "mask": png, "preview": png}
    assert c.post(path + "/renders", json=payload).status_code == 422
    assert not calls
    payload["confirmed"] = True
    response = c.post(path + "/renders", json=payload)
    assert response.status_code == 200, response.text
    job = response.json()
    assert job["status"] == "queued"
    assert c.post(path + "/renders", json=payload).json() == job
    assert len(calls) == 1
    assert c.post(path + "/renders", json={**payload, "prompt": "Changed"}).status_code == 409

    async def poll(*_):
        return "complete", buf.getvalue()

    monkeypatch.setattr(providers, "poll_image", poll)
    url = path + "/scene/renders/" + job["id"]
    assert c.get(url).json()["status"] == "complete"
    assert c.get(url + "/result.png").content == buf.getvalue()
    assert c.get(url + "/manifest.json").json()["sceneRevision"] == 1


def test_room_context_survives_reextraction(client, monkeypatch):
    from app import plan_api
    from app.plan_model import PlanModel

    c, bid = client
    path = f"/blueprints/{bid}/plan"
    original = c.put(path, json={"expectedRevision": 0, "model": plan(scale=reference())}).json()["model"]
    original["rooms"][0].update({"roomType": "bedroom", "label": "Main bedroom", "ceilingHeightM": 2.65})
    original["roomZones"] = [{"id": "open-space", "roomType": "corridor",
                               "polygon": [{"x": 50, "y": 50}, {"x": 90, "y": 50}, {"x": 90, "y": 90}]}]
    saved = c.put(path, json={"expectedRevision": 1, "model": original})
    assert saved.status_code == 200

    async def fresh(*args, **kwargs):
        data = plan()
        # Simulate regenerated wall IDs with the same room footprint.
        for wall in data["walls"]:
            wall["id"] += "-new"
        return PlanModel.model_validate(data)

    monkeypatch.setattr(plan_api, "run_worker", fresh)
    response = c.post(path + "/extract?expected_revision=2")
    assert response.status_code == 200, response.text
    model = response.json()["model"]
    assert model["rooms"][0]["roomType"] == "bedroom"
    assert model["rooms"][0]["label"] == "Main bedroom"
    assert model["rooms"][0]["ceilingHeightM"] == 2.65
    assert model["roomZones"][0]["roomType"] == "corridor"


def test_fixture_review_scan_does_not_edit_scene(client, monkeypatch):
    import app.fixture_detection as detector
    from app.fixture_detection import Hit

    c, bid = client
    path = f"/blueprints/{bid}"
    scan = path + "/scene/fixture-suggestions"
    assert c.get(scan, params={"plan_revision": 1}).status_code == 409
    assert c.put(path + "/plan", json={"expectedRevision": 0, "model": plan(scale=reference())}).status_code == 200

    def fixtures(gray, model):
        assert gray.shape == (600, 800)
        assert model.scale.meters_per_pixel == .01
        return [Hit("bed", .7, 215, 150, 1.62, 2.06, 270)]

    monkeypatch.setattr(detector, "for_plan", fixtures)
    response = c.get(scan, params={"plan_revision": 1})
    assert response.status_code == 200, response.text
    proposal, = response.json()["suggestions"]
    assert proposal["position"] == {"x": 215, "y": 150}
    assert proposal["rotation"] == -90
    assert proposal["mattressDepth"] < proposal["depth"] * .96
    assert c.get(scan, params={"plan_revision": 1}).json() == response.json()
    assert c.get(path + "/scene").json()["config"]["objects"] == []
    config = {"dismissedFixtureIds": [proposal["id"]]}
    assert c.put(path + "/scene", json={"expectedRevision": 0, "planRevision": 1, "config": config}).status_code == 200
    assert c.get(path + "/scene").json()["config"]["dismissedFixtureIds"] == [proposal["id"]]
