import base64
import io
import pytest

from PIL import Image

from app import providers, comfy, local_comfy
from app.config import settings
from test_plan_api import client, plan, reference  # noqa: F401


def test_recover_local_render_without_resubmitting(client, monkeypatch, tmp_path):
    import json
    from sqlmodel import Session
    from app import main
    from app.models import SceneRenderJob

    c, bid = client
    monkeypatch.setattr(settings, "storage_path", str(tmp_path))
    lookups = []
    with Session(main.engine) as session:
        job = SceneRenderJob(blueprint_id=bid, request_key="original", input_hash="example",
                             scene_revision=1, plan_revision=1, view_id="view", name="Render", prompt="",
                             provider_model=local_comfy.MODEL, status="failed")
        session.add(job)
        session.commit()
        job_id = job.id
    folder = tmp_path / bid / "scene-renders" / job_id
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({}))
    image = io.BytesIO()
    Image.new("RGB", (4, 4)).save(image, format="PNG")
    async def find(key):
        lookups.append(key)
        return ("receipt", "history", "history") if len(lookups) > 1 else None
    async def poll(url):
        assert url == "history"
        return "complete", image.getvalue()
    async def forbidden(*args, **kwargs):
        pytest.fail("Recovery submitted a render")
    monkeypatch.setattr(local_comfy, "find_receipt", find)
    monkeypatch.setattr(local_comfy, "poll", poll)
    monkeypatch.setattr(local_comfy, "generate", forbidden)
    path = f"/blueprints/{bid}/scene/renders/{job_id}"
    assert c.post(path + "/recover").status_code == 409
    assert c.get(path).json()["status"] == "failed"
    assert c.post(path + "/recover").json()["status"] == "complete"
    assert c.post(path + "/recover").json()["status"] == "complete"
    assert lookups == [job_id, job_id]
    assert c.get(path + "/result.png").content == image.getvalue()


def test_floor_material_overrides_round_trip(client):
    c, bid = client
    path = f"/blueprints/{bid}"
    saved_plan = c.put(path + "/plan", json={"expectedRevision": 0, "model": plan(scale=reference())})
    assert saved_plan.status_code == 200
    room_id = saved_plan.json()["model"]["rooms"][0]["id"]
    tile = {"kind": "tile", "color": "#c8bca7", "widthM": .45, "lengthM": .6}
    config = {"floorFinish": "oak", "roomFloorMaterials": {room_id: tile}}
    first = c.put(path + "/scene", json={"expectedRevision": 0, "planRevision": 1, "config": config})
    assert first.status_code == 200, first.text
    config = first.json()["config"]
    config["floorMaterial"] = {"kind": "concrete", "color": "#a9a6a0", "widthM": 1, "lengthM": 1}
    request = {"expectedRevision": 1, "planRevision": 1, "config": config}
    assert c.put(path + "/scene", json=request).status_code == 200
    assert c.get(path + "/scene").json()["config"]["roomFloorMaterials"] == {room_id: tile}
    config["floorMaterial"]["widthM"] = 0
    assert c.put(path + "/scene", json={**request, "expectedRevision": 2}).status_code == 422


def test_room_finish_survives_wall_segment_split_and_can_be_reassigned_after_room_split(client):
    c, bid = client
    path = f"/blueprints/{bid}"
    model = c.put(path + "/plan", json={"expectedRevision": 0, "model": plan(scale=reference())}).json()["model"]
    room_id = model["rooms"][0]["id"]
    tile = {"kind": "tile", "color": "#c8bca7", "widthM": .45, "lengthM": .6}
    assignment = {room_id: tile}
    config = {"roomFloorMaterials": {"unknown-room": tile}}
    payload = {"expectedRevision": 0, "planRevision": 1, "config": config}
    assert c.put(path + "/scene", json=payload).status_code == 422
    config["roomFloorMaterials"] = assignment
    assert c.put(path + "/scene", json=payload).status_code == 200

    # A collinear segment changes the wall IDs without changing the room.
    model["nodes"].append({"id": "top", "x": 400, "y": 100})
    wall = model["walls"][0]
    model["walls"].append({**wall, "id": "top-right", "a": "top"})
    wall["b"] = "top"
    model["rooms"][0]["id"] = "client-preview-id"
    result = c.put(path + "/plan", json={"expectedRevision": 1, "model": model})
    assert result.status_code == 200, result.text
    model = result.json()["model"]
    assert model["rooms"][0]["id"] == room_id
    assert c.get(path + "/plan").json()["model"]["rooms"][0]["id"] == room_id
    assert c.get(path + "/scene").json()["config"]["roomFloorMaterials"] == assignment

    # A partition splits the actual room. Keep the original assignment for review.
    model["nodes"].append({"id": "bottom", "x": 400, "y": 500})
    wall = model["walls"][2]
    model["walls"].extend([
        {**wall, "id": "bottom-left", "a": "bottom"},
        {**wall, "id": "partition", "a": "top", "b": "bottom"},
    ])
    wall["b"] = "bottom"
    result = c.put(path + "/plan", json={"expectedRevision": 2, "model": model})
    assert result.status_code == 200, result.text
    ids = [room["id"] for room in result.json()["model"]["rooms"]]
    assert len(ids) == 2 and room_id not in ids
    payload.update(expectedRevision=1, planRevision=3)
    assert c.put(path + "/scene", json=payload).status_code == 200
    assert c.get(path + "/scene").json()["config"]["roomFloorMaterials"] == assignment
    payload["expectedRevision"] = 2
    config["roomFloorMaterials"] = {ids[0]: tile}
    assert c.put(path + "/scene", json=payload).status_code == 200
    assert c.get(path + "/scene").json()["config"]["roomFloorMaterials"] == {ids[0]: tile}

    model = result.json()["model"]
    model["walls"] = [wall for wall in model["walls"] if wall["id"] != "partition"]
    result = c.put(path + "/plan", json={"expectedRevision": 3, "model": model})
    assert result.status_code == 200, result.text
    merged_rooms = result.json()["model"]["rooms"]
    assert len(merged_rooms) == 1 and merged_rooms[0]["id"] not in ids
    assert c.get(path + "/scene").json()["config"]["roomFloorMaterials"] == {ids[0]: tile}


@pytest.mark.parametrize('provider', ['fal', 'comfy', 'local-comfy', 'masked-local'])
def test_scene_render_is_revisioned_and_does_not_resubmit(client, monkeypatch, tmp_path, provider):
    masked = provider == 'masked-local'
    if masked:
        provider = 'local-comfy'
    c, bid = client
    path = f"/blueprints/{bid}"
    monkeypatch.setattr(settings, "image_api_key", "mock")
    monkeypatch.setattr(settings, 'comfy_api_key', 'mock')
    monkeypatch.setattr(settings, 'image_provider', provider)
    monkeypatch.setattr(settings, "storage_path", str(tmp_path))
    assert c.get('/health').json()['image_configured'] is True
    render_settings = c.get(path + '/scene/render-settings').json()
    assert render_settings['provider'] == provider
    assert render_settings['configured'] is True
    calls = []

    async def generate(depth, prompt, *, model):
        image = Image.open(io.BytesIO(depth))
        assert image.mode == "L" and image.size == (1024, 768)
        assert image.getpixel((0, 0)) > image.getpixel((1, 0))
        calls.append(prompt)
        return "mock-job", "https://queue.fal.run/status", "https://queue.fal.run/result"

    monkeypatch.setattr(providers, "generate_image", generate)
    async def generate_comfy(depth, prompt, *, request_key, preview_png=None):
        if masked:
            assert Image.open(io.BytesIO(preview_png)).size == (192, 192)
            assert Image.open(io.BytesIO(depth)).size == (192, 192)
            calls.append(prompt)
            return "local-job", "local-status", "local-result"
        assert request_key
        return await generate(depth, prompt, model=comfy.MODEL)
    monkeypatch.setattr(comfy, 'generate', generate_comfy)
    monkeypatch.setattr(local_comfy, 'generate', generate_comfy)
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
    if masked:
        payload["targetObjectId"] = "bed"
        assert c.post(path + "/renders", json=payload).status_code == 422
        ids = Image.new("RGB", image.size)
        ids.paste((0, 3, 232), (10, 10, 50, 50))
        mask_bytes = io.BytesIO()
        ids.save(mask_bytes, format="PNG")
        payload["mask"] = base64.b64encode(mask_bytes.getvalue()).decode()
    response = c.post(path + "/renders", json=payload)
    assert response.status_code == 200, response.text
    job = response.json()
    assert job["status"] == "queued"
    assert c.post(path + "/renders", json=payload).json() == job
    # Retrying identical inputs with different JSON key order/whitespace is still one job.
    import json
    reordered = json.dumps(dict(reversed(list(payload.items()))), indent=2)
    retry = c.post(path + "/renders", content=reordered, headers={'content-type': 'application/json'})
    assert retry.json() == job
    assert len(calls) == 1
    assert c.post(path + "/renders", json={**payload, "prompt": "Changed"}).status_code == 409

    async def poll(*args):
        if masked:
            assert args[1] == (192, 192)
            patch = io.BytesIO()
            Image.new("RGB", args[1], "red").save(patch, format="PNG")
            return "complete", patch.getvalue()
        return "complete", buf.getvalue()

    monkeypatch.setattr(providers, "poll_image", poll)
    monkeypatch.setattr(comfy, 'poll', poll)
    monkeypatch.setattr(local_comfy, 'poll', poll)
    url = path + "/scene/renders/" + job["id"]
    assert c.get(url).json()["status"] == "complete"
    result = c.get(url + "/result.png").content
    if masked:
        output = Image.open(io.BytesIO(result))
        assert output.size == image.size
        assert output.getpixel((20, 20)) == (255, 0, 0)
        assert output.getpixel((51, 51)) == image.getpixel((51, 51))
    else:
        assert result == buf.getvalue()
    assert c.get(url + "/manifest.json").json()["sceneRevision"] == 1
    manifest = c.get(url + '/manifest.json').json()
    assert manifest['provider'] == provider
    assert manifest['architectureReview']['status'] == 'draft'
    assert manifest['architectureReview']['revision'] == 1
    assert manifest['inputHash'].startswith('v2:')
    import hashlib
    assert manifest['captureHashes']['depth.png'] == hashlib.sha256(buf.getvalue()).hexdigest()

    additional = {**config["views"][0], "id": "new-view"}
    revised = {**config, "views": [*config["views"], additional]}
    assert c.put(path + "/scene", json={"expectedRevision": 1, "planRevision": 1, "config": revised}).status_code == 200
    assert c.get(path + "/scene/renders").json()[0]["compatibleSceneRevision"] == 2
    revised["views"][0]["yaw"] += 10
    assert c.put(path + "/scene", json={"expectedRevision": 2, "planRevision": 1, "config": revised}).status_code == 200
    assert "compatibleSceneRevision" not in c.get(path + "/scene/renders").json()[0]


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


def test_save_furniture_catalog_items_preserves_metric_dimensions(client):
    c, bid = client
    path = f"/blueprints/{bid}"
    assert c.put(path + "/plan", json={"expectedRevision": 0, "model": plan(scale=reference())}).status_code == 200
    objects = [
        {"id": "sofa", "kind": "sofa", "position": {"x": 270, "y": 200},
         "width": 2.1, "depth": .92, "height": .85, "rotation": 15},
        {"id": "table", "kind": "table", "position": {"x": 470, "y": 260},
         "width": 1.4, "depth": .8, "height": .75, "rotation": 0},
    ]
    view = {
        "id": "corner", "name": "Corner view", "position": {"x": 150, "y": 120},
        "yaw": 45, "pitch": -5, "horizontalFov": 120, "eyeHeight": 1.6,
    }
    response = c.put(path + "/scene", json={
        "expectedRevision": 0, "planRevision": 1, "config": {"objects": objects, "views": [view]},
    })
    assert response.status_code == 200, response.text
    saved = c.get(path + "/scene").json()["config"]
    assert saved["views"] == [view]
    assert [{key: item[key] for key in source} for item, source in zip(saved["objects"], objects)] == objects


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


def test_optional_fixture_weights_stay_review_only(client, monkeypatch):
    from app import fixture_weights
    from app.fixture_detection import Hit
    c, bid = client
    path = f"/blueprints/{bid}"
    assert c.put(path + '/plan', json={'expectedRevision': 0, 'model': plan(scale=reference())}).status_code == 200
    monkeypatch.setattr(settings, 'fixture_yolo_weights', '/trusted/model.pt')
    monkeypatch.setattr(fixture_weights, 'detect', lambda gray, mpp, path: [Hit('vanity', .8, 250, 250, .8, .5, 0)])
    response = c.get(path + '/scene/fixture-suggestions', params={'plan_revision': 1})
    assert response.status_code == 200
    assert response.json()['source'] == 'local-yolo-weights'
    assert response.json()['orientationNeedsReview']
    assert response.json()['suggestions'][0]['kind'] == 'vanity'
    assert c.get(path + '/scene').json()['config']['objects'] == []
    def missing(*args):
        raise ValueError('missing')
    monkeypatch.setattr(fixture_weights, 'detect', missing)
    assert c.get(path + '/scene/fixture-suggestions', params={'plan_revision': 1}).status_code == 503
