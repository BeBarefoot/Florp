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
