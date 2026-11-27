import uuid

from test_plan_api import client, plan, reference


def test_variant_is_independent_idempotent_and_keeps_its_original_comparison(client):
    c, bid = client
    pid = c.get("/projects").json()[0]["id"]
    key = str(uuid.uuid4())
    path = f"/blueprints/{bid}"
    baseline = c.put(path + "/plan", json={"expectedRevision": 0, "model": plan(scale=reference())}).json()
    draft = plan(scale=reference())
    draft["nodes"] += [{"id": "partition-a", "x": 200, "y": 200}, {"id": "partition-b", "x": 500, "y": 200}]
    draft["walls"] += [{"id": "partition", "a": "partition-a", "b": "partition-b", "thicknessPx": 10}]
    body = {"requestId": key, "title": "Closet option A", "planRevision": 1, "sceneRevision": 0,
            "metrics": {"passage": .92, "storageDepth": .6, "moved": 0}, "plan": draft,
            "scene": {"objects": [{"id": "closet", "kind": "wardrobe", "position": {"x": 350, "y": 160},
                                   "rotation": 0, "width": 2.4, "depth": .6, "height": 2.1}]}}
    response = c.post(path + "/variants", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["id"] == key
    assert c.post(path + "/variants", json=body).json() == response.json()
    assert c.get(path + "/plan").json() == baseline
    assert [bp["id"] for bp in c.get(f"/projects/{pid}/blueprints").json()] == [bid]
    variant = c.get(f"/design-variants/{key}").json()
    assert variant["baseline"]["plan"] == baseline["model"]
    assert len(variant["variant"]["plan"]["walls"]) == 5
    assert variant["variant"]["scene"]["objects"][0]["kind"] == "wardrobe"
    assert c.get(f"/blueprints/{key}/plan/export").status_code == 200
    assert c.get(f"/blueprints/{key}/preview").status_code == 200
    assert c.put(path + "/plan", json={"expectedRevision": 1, "model": plan(scale=reference(7))}).status_code == 200
    assert c.get(f"/design-variants/{key}").json()["baseline"]["plan"] == baseline["model"]
    assert c.post(path + "/variants", json={**body, "requestId": str(uuid.uuid4())}).status_code == 409
