"""Revisioned interior scenes and explicitly authorized render submissions."""
import base64
import binascii
import hashlib
import io
import json
from datetime import timezone
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic.alias_generators import to_camel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from . import providers, comfy
from .config import settings
from .depth import control_depth
from .models import SceneRevision, SceneRenderJob
from .plan_api import blueprint, get_engine, latest
from .plan_model import PlanModel, Pt

router = APIRouter(prefix="/blueprints/{bid}")
MAX_PNG = 4 * 1024 * 1024


class Data(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, allow_inf_nan=False)


class View(Data):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    name: str = Field(min_length=1, max_length=80)
    position: Pt
    yaw: float = Field(ge=-360, le=360)
    pitch: float = Field(ge=-45, le=30)
    horizontal_fov: float = Field(ge=55, le=110)
    eye_height: float = Field(ge=0.8, le=2.2)


class SceneObject(Data):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    kind: Literal["bed", "wardrobe", "toilet", "vanity", "shower", "bathtub"]
    position: Pt
    rotation: float = Field(ge=-360, le=360)
    width: float = Field(gt=0.05, le=8)
    depth: float = Field(gt=0.05, le=8)
    height: float = Field(gt=0.05, le=5)
    mattress_width: float | None = Field(default=None, gt=0.05, le=8)
    mattress_depth: float | None = Field(default=None, gt=0.05, le=8)


class Scene(Data):
    views: list[View] = Field(default_factory=list, max_length=30)
    objects: list[SceneObject] = Field(default_factory=list, max_length=100)
    style: str = Field(default="", max_length=1200)
    closed_door_ids: list[str] = Field(default_factory=list, max_length=500)
    dismissed_fixture_ids: list[str] = Field(default_factory=list, max_length=500)


class SaveScene(Data):
    expected_revision: int = Field(ge=0)
    plan_revision: int = Field(gt=0)
    config: Scene


def current(s, bid):
    return s.exec(select(SceneRevision).where(SceneRevision.blueprint_id == bid)
                  .order_by(SceneRevision.revision.desc())).first()


@router.get("/scene")
def get_scene(bid: str):
    with Session(get_engine()) as s:
        blueprint(s, bid)
        row = current(s, bid)
        return {"revision": row.revision, "planRevision": row.plan_revision, "config": row.config} if row else {
            "revision": 0, "planRevision": None, "config": Scene().model_dump(by_alias=True)}


@router.put("/scene")
def save_scene(bid: str, body: SaveScene):
    with Session(get_engine()) as s:
        bp = blueprint(s, bid)
        plan = latest(s, bid)
        if not plan or plan.revision != body.plan_revision:
            raise HTTPException(409, "Save the current floor plan before saving the scene")
        if not plan.model.get("scale", {}).get("reference"):
            raise HTTPException(422, "Calibrate the floor plan before saving a scene")
        if any(o.kind == "bed" and ((o.mattress_width or 0) > o.width or (o.mattress_depth or 0) > o.depth * .96) for o in body.config.objects):
            raise HTTPException(422, "The mattress must fit within the bed frame")
        old = current(s, bid)
        if (old.revision if old else 0) != body.expected_revision:
            raise HTTPException(409, "The scene has changed. Reload it before saving.")
        for items in (body.config.views, body.config.objects):
            if len({item.id for item in items}) != len(items) or any(
                not (0 <= item.position.x <= bp.width and 0 <= item.position.y <= bp.height) for item in items
            ):
                raise HTTPException(422, "Scene positions or IDs are invalid")
        data = body.config.model_dump(by_alias=True)
        rev = body.expected_revision + 1
        s.add(SceneRevision(blueprint_id=bid, revision=rev, plan_revision=body.plan_revision, config=data))
        try:
            s.commit()
        except IntegrityError as exc:
            raise HTTPException(409, "The scene has changed. Reload it before saving.") from exc
        return {"revision": rev, "planRevision": body.plan_revision, "config": data}


@router.get("/scene/fixture-suggestions")
def fixture_suggestions(bid: str, plan_revision: int):
    """Inspect the original local blueprint for reviewable scene objects."""
    from .fixture_detection import HEIGHT, for_plan

    with Session(get_engine()) as s:
        bp = blueprint(s, bid)
        plan = latest(s, bid)
        if not plan or plan.revision != plan_revision:
            raise HTTPException(409, "Save or reload the floor plan before scanning.")
        model = PlanModel.model_validate(plan.model)
        path = bp.preview_path
    if not model.scale.meters_per_pixel:
        raise HTTPException(422, "Calibrate the floor plan before scanning for furniture.")
    try:
        with Image.open(path) as image:
            dims = model.image_transform
            if image.size != (dims.width, dims.height):
                raise HTTPException(409, "The saved plan and source image do not match.")
            gray = np.array(image.convert("L"))
    except OSError as exc:
        raise HTTPException(404, "The blueprint image is not available.") from exc
    source = "local-symbol-matcher"
    if settings.fixture_yolo_weights:
        from .fixture_weights import detect, contextual_hits
        try:
            hits = contextual_hits(detect(gray, model.scale.meters_per_pixel, settings.fixture_yolo_weights), model)
        except (ImportError, ValueError, OSError, RuntimeError) as exc:
            raise HTTPException(503, "Fixture detector unavailable. Install the pretrained-yolo extra and configure trusted local FIXTURE_YOLO_WEIGHTS.") from exc
        source = "local-yolo-weights"
    else:
        hits = for_plan(gray, model)
    proposals = []
    for h in hits:
        # The ID is scoped to the blueprint by the scene record. It stays
        # stable across identical scans so accepted or dismissed items stay hidden.
        token = f"{h.kind}:{round(h.x/4)}:{round(h.y/4)}"
        fixture_id = "fixture-" + hashlib.sha256(token.encode()).hexdigest()[:20]
        item = SceneObject(id=fixture_id, kind=h.kind, position=Pt(x=h.x, y=h.y),
                           width=h.width, depth=h.depth, height=HEIGHT[h.kind],
                           rotation=h.rotation if h.rotation <= 180 else h.rotation-360,
                           mattress_width=round(h.width*.94, 2) if h.kind == "bed" else None,
                           mattress_depth=round(h.depth*.93, 2) if h.kind == "bed" else None)
        proposals.append(item.model_dump(by_alias=True))
    return {"planRevision": plan_revision, "suggestions": proposals, "source": source,
            "orientationNeedsReview": bool(settings.fixture_yolo_weights)}


@router.get("/scene/render-settings")
def render_settings(bid: str):
    with Session(get_engine()) as s:
        blueprint(s, bid)
    return {**comfy.render_config(),
            "width": providers.FRAME_WIDTH, "height": providers.FRAME_HEIGHT}


class Submit(Data):
    request_key: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    scene_revision: int = Field(gt=0)
    view_id: str
    name: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1, max_length=10000)
    depth: str
    mask: str
    preview: str
    confirmed: Literal[True]


def png(value):
    try:
        raw = base64.b64decode(value, validate=True)
        if len(raw) > MAX_PNG:
            raise ValueError()
        with Image.open(io.BytesIO(raw), formats=["PNG"]) as im:
            if im.size != (providers.FRAME_WIDTH, providers.FRAME_HEIGHT):
                raise ValueError()
            im.load()
            rgb = np.array(im.convert("RGB"))
        return raw, rgb
    except (ValueError, binascii.Error, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, "Invalid render capture PNG or frame size") from exc


def directory(bid, job_id):
    return Path(settings.storage_path) / bid / "scene-renders" / job_id


def public(j):
    return {"id": j.id, "viewId": j.view_id, "sceneRevision": j.scene_revision, "planRevision": j.plan_revision,
            "name": j.name, "prompt": j.prompt, "model": j.provider_model, "status": j.status, "error": j.error}


@router.post("/renders")
async def submit(bid: str, request: Request):
    payload = bytearray()
    async for chunk in request.stream():
        if len(payload) + len(chunk) > 17 * 1024 * 1024:
            raise HTTPException(413, "Render captures are too large")
        payload.extend(chunk)
    try:
        body = Submit.model_validate_json(payload)
    except ValidationError as exc:
        raise HTTPException(422, "Invalid render request or missing consent") from exc
    fingerprint = hashlib.sha256(payload).hexdigest()

    def existing(s):
        return s.exec(select(SceneRenderJob).where(SceneRenderJob.blueprint_id == bid,
                      SceneRenderJob.request_key == body.request_key)).first()

    def duplicate(job):
        if job.input_hash != fingerprint:
            raise HTTPException(409, "This render request key belongs to different inputs")
        return public(job)

    with Session(get_engine()) as s:
        blueprint(s, bid)
        prior = existing(s)
        if prior:
            return duplicate(prior)
        scene = s.exec(select(SceneRevision).where(SceneRevision.blueprint_id == bid,
                       SceneRevision.revision == body.scene_revision)).first()
        if not scene or not any(v["id"] == body.view_id for v in scene.config["views"]):
            raise HTTPException(422, "Save this camera view before rendering")
        config = comfy.render_config()
        if not config['configured']:
            key = 'COMFY_API_KEY' if config['provider'] == 'comfy' else 'IMAGE_API_KEY'
            raise HTTPException(503, f"Set {key} in the API environment to enable generation")
        raw_depth, rgb = png(body.depth)
        mask, _ = png(body.mask)
        preview, _ = png(body.preview)
        try:
            normalized, (near, far) = control_depth(rgb)
        except ValueError as exc:
            raise HTTPException(422, "No valid scene depth was captured") from exc
        control = io.BytesIO()
        Image.fromarray(normalized).save(control, format="PNG")
        job = SceneRenderJob(blueprint_id=bid, request_key=body.request_key, input_hash=fingerprint,
                             scene_revision=scene.revision, plan_revision=scene.plan_revision,
                             view_id=body.view_id, name=body.name, prompt=body.prompt,
                             provider_model=config['model'])
        manifest = {"scene": scene.config, "depthEncoding": "RGB24 view-space millimetres; zero is background",
                    "maskEncoding": "RGB24 IDs; 1 structural details, 2.. room floors, 1000.. scene objects, 2000.. walls",
                    "depthRangeMm": [near, far], "frame": [providers.FRAME_WIDTH, providers.FRAME_HEIGHT],
                    "provider": config['provider'], **public(job)}
        s.add(job)
        try:
            s.commit()
        except IntegrityError:
            s.rollback()
            prior = existing(s)
            if prior:
                return duplicate(prior)
            raise HTTPException(409, "Render request conflict")
        job_id = job.id

    folder = directory(bid, job_id)
    try:
        folder.mkdir(parents=True)
        for name, data in (("depth.png", raw_depth), ("mask.png", mask), ("preview.png", preview),
                           ("control.png", control.getvalue())):
            (folder / name).write_bytes(data)
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        if manifest['provider'] == 'comfy':
            result = await comfy.generate(control.getvalue(), body.prompt, request_key=job_id)
        else:
            result = await providers.generate_image(control.getvalue(), body.prompt, model=manifest["model"])
    except Exception as exc:
        # Submission may have reached the provider even when its response was lost.
        # Never automatically resubmit a potentially billable request.
        result = None
        error = providers.render_error(exc)
    with Session(get_engine()) as s:
        job = s.get(SceneRenderJob, job_id)
        if job is None:
            raise HTTPException(404, "Render job not found")
        if result:
            job.provider_job_id, job.status_url, job.response_url = result
            job.status = "queued"
        else:
            job.status, job.error = "failed", error
        s.add(job)
        s.commit()
        return public(job)


@router.get("/scene/renders")
def jobs(bid: str):
    with Session(get_engine()) as s:
        return [public(j) for j in s.exec(select(SceneRenderJob).where(SceneRenderJob.blueprint_id == bid)
                                        .order_by(SceneRenderJob.created_at.desc()).limit(100)).all()]


@router.get("/scene/renders/{job_id}")
async def poll(bid: str, job_id: str):
    from datetime import datetime
    import httpx

    with Session(get_engine()) as s:
        j = s.get(SceneRenderJob, job_id)
        if not j or j.blueprint_id != bid:
            raise HTTPException(404, "Render job not found")
        age = (datetime.now(timezone.utc) - j.created_at.replace(tzinfo=timezone.utc)).total_seconds()
        if j.status in ("submitting", "queued", "running") and age > 1200:
            j.status, j.error = "failed", "Render timed out. Check your provider dashboard before retrying."
        elif j.status in ("queued", "running"):
            try:
                if j.provider_model.startswith('comfy:'):
                    status, image = await comfy.poll(j.status_url)
                else:
                    status, image = await providers.poll_image(j.status_url, j.response_url)
                if image is not None:
                    # Atomic replacement also handles two browser tabs polling at once.
                    import tempfile
                    folder = directory(bid, job_id)
                    with tempfile.NamedTemporaryFile(dir=folder, delete=False) as f:
                        f.write(image)
                    Path(f.name).replace(folder / "result.png")
                j.status, j.error = status, None
            except (httpx.TimeoutException, httpx.NetworkError):
                return {**public(j), "error": "Provider temporarily unreachable; will check again."}
            except Exception as exc:
                j.status, j.error = "failed", providers.render_error(exc)
        s.add(j)
        s.commit()
        return public(j)


@router.get("/scene/renders/{job_id}/{asset}")
def artifact(bid: str, job_id: str, asset: Literal["preview.png", "result.png", "depth.png", "mask.png", "manifest.json"]):
    with Session(get_engine()) as s:
        job = s.get(SceneRenderJob, job_id)
        if not job or job.blueprint_id != bid:
            raise HTTPException(404, "Render job not found")
    path = directory(bid, job_id) / asset
    if not path.is_file():
        raise HTTPException(404, "Capture not available")
    return FileResponse(path)
