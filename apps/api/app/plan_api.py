"""PlanModel v2 routes: one append-only, revisioned model per blueprint."""

from __future__ import annotations
import asyncio, hashlib, json, logging, math, os, shutil, signal, sys, tempfile
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from shapely.geometry import LineString
from shapely.ops import unary_union
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select
from .models import Blueprint, PlanRevision
from .plan_model import PlanModel, ImageTransform, Reference, Pt, wall_length
from .plan_derive import derive
from .plan_reconstruct import reconstruct, configured_config
from .plan_workspace import Document

router = APIRouter()
WORKER_BUDGET_S = 20


def get_engine():
    from .main import engine

    return engine


class Save(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    expected_revision: int = Field(ge=0)
    model: PlanModel


def latest(s, bid):
    return s.exec(
        select(PlanRevision)
        .where(PlanRevision.blueprint_id == bid)
        .order_by(PlanRevision.revision.desc())
    ).first()


def store(s, bid, model: PlanModel, revision: int) -> dict:
    model = model.model_copy(update={"revision": revision, "id": bid})
    row = PlanRevision(blueprint_id=bid, revision=revision, model=model.dump())
    s.add(row)
    try:
        s.commit()
    except IntegrityError:
        raise HTTPException(409, "Revision changed; reload before saving")
    return {"revision": revision, "model": row.model}


def blueprint(s, bid) -> Blueprint:
    bp = s.get(Blueprint, bid)
    if not bp:
        raise HTTPException(404, "Plan not found")
    return bp


async def run_worker(path: str, roi=None) -> Document:
    """Run extraction in an isolated, time-boxed subprocess (optional building outline ``roi``)."""
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "result.json"
        extra = []
        if roi:
            roi_file = Path(tmp) / "roi.json"
            roi_file.write_text(json.dumps([[p.x, p.y] for p in roi]))
            extra = [str(roi_file)]
        env = {
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
        }
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.workspace_worker",
            path,
            str(output),
            *extra,
            env=env,
            start_new_session=True,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), WORKER_BUDGET_S)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await proc.communicate()
            raise HTTPException(
                504, "Extraction exceeded its budget; saved geometry is unchanged"
            )
        if proc.returncode:
            logging.getLogger(__name__).error(
                "Extraction worker failed (exit %s): %s",
                proc.returncode, stderr.decode("utf-8", errors="replace")[-12000:],
            )
            from .config import settings

            if settings.workspace_semantic_source or settings.workspace_semantic_weights:
                raise HTTPException(
                    503,
                    "Local semantic evaluation failed. Check the trusted source, checkpoint, optional runtime and device configuration. Saved geometry is unchanged.",
                )
            raise HTTPException(
                500,
                "The extraction worker failed. Saved geometry is unchanged. The API log contains the failure details.",
            )
        return Document.model_validate_json(output.read_bytes())


@router.get("/blueprints/{bid}/plan")
def load(bid: str):
    with Session(get_engine()) as s:
        blueprint(s, bid)
        row = latest(s, bid)
        return {"revision": row.revision, "model": row.model} if row else {
            "revision": 0,
            "model": None,
        }


@router.put("/blueprints/{bid}/plan")
def save(bid: str, body: Save):
    with Session(get_engine()) as s:
        bp = blueprint(s, bid)
        t = body.model.image_transform
        if (t.width, t.height) != (bp.width, bp.height):
            raise HTTPException(422, "Source dimensions changed")
        row = latest(s, bid)
        current = row.revision if row else 0
        if current != body.expected_revision:
            raise HTTPException(
                409,
                "A newer revision exists. Reload before saving; local changes are retained.",
            )
        return store(s, bid, derive(body.model), current + 1)


class Extract(BaseModel):
    """Optional building outline (pixel polygon) that replaces the detected envelope."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    envelope: list[Pt] | None = Field(default=None, min_length=3, max_length=64)


@router.post("/blueprints/{bid}/plan/extract")
async def extract(bid: str, expected_revision: int = 0, body: Extract | None = None):
    with Session(get_engine()) as s:
        bp = blueprint(s, bid)
        row = latest(s, bid)
        if (row.revision if row else 0) != expected_revision:
            raise HTTPException(409, "Plan changed before extraction")
        path = bp.preview_path
        previous = PlanModel.model_validate(row.model) if row else None
        if body and body.envelope:
            from .envelope import validate_polygon
            try:
                validate_polygon([(p.x,p.y) for p in body.envelope],(bp.height,bp.width))
            except ValueError as exc:
                raise HTTPException(422,str(exc)) from exc
    try:
        config=configured_config()
    except (OSError,ValueError) as exc:
        raise HTTPException(503,'Opening approval profile is unavailable or invalid; saved geometry is unchanged') from exc
    doc = await run_worker(path, body.envelope if body else None)
    model = reconstruct(doc, bid, config)
    if previous and previous.scale.reference:
        model.scale = previous.scale.model_copy(deep=True)
        model = PlanModel.model_validate(model.dump())
    with Session(get_engine()) as s:
        row = latest(s, bid)
        if (row.revision if row else 0) != expected_revision:
            raise HTTPException(409, "Plan changed during extraction; saved edits retained")
        return store(s, bid, model, expected_revision + 1)


@router.get("/blueprints/{bid}/plan/history")
def history(bid: str):
    with Session(get_engine()) as s:
        return [
            {"revision": r.revision, "createdAt": r.created_at, "model": r.model}
            for r in s.exec(
                select(PlanRevision)
                .where(PlanRevision.blueprint_id == bid)
                .order_by(PlanRevision.revision.desc())
            ).all()
        ]


@router.get("/blueprints/{bid}/info")
def info(bid: str):
    with Session(get_engine()) as s:
        bp = blueprint(s, bid)
        return {
            "id": bp.id,
            "project_id": bp.project_id,
            "filename": bp.filename,
            "width": bp.width,
            "height": bp.height,
        }


def wall_footprints(model: PlanModel):
    nodes = {n.id: n for n in model.nodes}
    for w in model.walls:
        a, b = nodes[w.a], nodes[w.b]
        yield w, LineString([(a.x, a.y), (b.x, b.y)]).buffer(
            w.thickness_px / 2, cap_style=2, join_style=2
        )


def opening_footprint(model: PlanModel, o):
    nodes = {n.id: n for n in model.nodes}
    w = next(x for x in model.walls if x.id == o.host_wall_id)
    a, b = nodes[w.a], nodes[w.b]
    length = wall_length(model, w, nodes)
    ux, uy = (b.x - a.x) / length, (b.y - a.y) / length
    p = (a.x + ux * o.offset_px, a.y + uy * o.offset_px)
    q = (a.x + ux * (o.offset_px + o.width_px), a.y + uy * (o.offset_px + o.width_px))
    return LineString([p, q]).buffer(w.thickness_px / 2 + 1, cap_style=2)


@router.get("/blueprints/{bid}/plan/export")
def export(bid: str):
    payload = load(bid)
    if not payload["model"]:
        raise HTTPException(422, "No plan to export")
    model = PlanModel.model_validate(payload["model"])
    mpp = model.scale.meters_per_pixel
    if not mpp:
        raise HTTPException(422, "Set one known measurement before metric export")
    if any(o.status == "proposed" for o in model.openings):
        raise HTTPException(
            422, "Approve or reject every proposed door and window before exporting."
        )
    from .deterministic_blueprint.export import normalize_metric, png, svg, dxf, bundle

    names = ["LAYER_WALLS_EXTERIOR", "LAYER_WALLS_INTERIOR", "LAYER_MAMAD_CONCRETE"]
    parts = {name: [] for name in names}
    for w, shape in wall_footprints(model):
        name = (
            "LAYER_MAMAD_CONCRETE"
            if w.material == "concrete"
            else "LAYER_WALLS_EXTERIOR"
            if w.exterior is True
            else "LAYER_WALLS_INTERIOR"
        )
        parts[name].append(shape)
    layers = {k: unary_union(v) for k, v in parts.items()}
    if all(g.is_empty for g in layers.values()):
        raise HTTPException(422, "No walls to export")
    cuts = unary_union(
        [opening_footprint(model, o) for o in model.openings if o.status == "confirmed"]
    )
    layers = {k: g.difference(cuts) for k, g in layers.items()}
    layers, bounds, report = normalize_metric(layers, 1 / mpp / 100)
    raster, meta = png(layers, bounds, 100)
    report.update({"revision": payload["revision"], "raster": meta, "plan": model.dump()})
    return Response(
        bundle(layers, bounds, report, raster, svg(layers, bounds, 100), dxf(layers, bounds)),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="florp-plan.zip"'},
    )


class Rectification(BaseModel):
    model_config = ConfigDict(
        extra="forbid", allow_inf_nan=False, alias_generator=to_camel, populate_by_name=True
    )
    corners: list[tuple[float, float]] = Field(min_length=4, max_length=4)
    page_aspect_ratio: float = Field(ge=0.1, le=10)
    expected_revision: int = Field(ge=0)


@router.post("/blueprints/{bid}/plan/straighten")
def straighten(bid: str, body: Rectification):
    """Create a new rectified source; the original plan and its revisions are kept."""
    import cv2, numpy as np
    from PIL import Image
    from .config import settings
    from .deterministic_blueprint.preprocess import decode, order_quad, transform_points

    with Session(get_engine()) as s:
        source = blueprint(s, bid)
        row = latest(s, bid)
        if (row.revision if row else 0) != body.expected_revision:
            raise HTTPException(409, "Save/reload the source before straightening")
        initial = PlanModel.model_validate(row.model) if row else None
        image = decode(Path(source.preview_path).read_bytes())
        h, w = image.shape[:2]
        q = order_quad(body.corners)
        if (
            not cv2.isContourConvex(q)
            or abs(cv2.contourArea(q)) < 0.1 * w * h
            or np.any(q < 0)
            or np.any(q[:, 0] > w - 1)
            or np.any(q[:, 1] > h - 1)
        ):
            raise HTTPException(422, "Select four corners enclosing the sheet, inside the image")
        vectors = np.roll(q, -1, axis=0) - q
        width = (np.linalg.norm(vectors[0]) + np.linalg.norm(vectors[2])) / 2
        height = width / body.page_aspect_ratio
        factor = min(1, 4000 / max(width, height))
        width = max(16, round(width * factor))
        height = max(16, round(height * factor))
        matrix = cv2.getPerspectiveTransform(
            q, np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]])
        )
        rectified = cv2.warpPerspective(image, matrix, (width, height), borderValue=(255, 255, 255))
        target = Blueprint(
            project_id=source.project_id,
            filename=source.filename + " — straightened",
            local_path="",
            preview_path="",
            width=width,
            height=height,
        )
        folder = Path(settings.storage_path) / target.id
        folder.mkdir(parents=True, exist_ok=False)
        reference = None
        if initial and initial.scale.reference:
            ref = initial.scale.reference
            pts = transform_points([(ref.p1.x, ref.p1.y), (ref.p2.x, ref.p2.y)], matrix)
            if (
                np.all(pts >= 0)
                and np.all(pts[:, 0] <= width - 1)
                and np.all(pts[:, 1] <= height - 1)
                and np.linalg.norm(pts[1] - pts[0]) >= 5
            ):
                reference = Reference(
                    p1=Pt(x=float(pts[0][0]), y=float(pts[0][1])),
                    p2=Pt(x=float(pts[1][0]), y=float(pts[1][1])),
                    length_meters=ref.length_meters,
                )
        try:
            raw = folder / ("original" + Path(source.local_path).suffix)
            shutil.copyfile(source.local_path, raw)
            preview = folder / "preview.png"
            Image.fromarray(cv2.cvtColor(rectified, cv2.COLOR_BGR2RGB)).save(preview)
            target.local_path = str(raw)
            target.preview_path = str(preview)
            (folder / "source-transform.json").write_text(
                json.dumps(
                    {
                        "parent_blueprint_id": bid,
                        "page_aspect_ratio": body.page_aspect_ratio,
                        "source_to_rectified": matrix.tolist(),
                        "rectified_to_source": np.linalg.inv(matrix).tolist(),
                        "source_sha256": hashlib.sha256(
                            Path(source.preview_path).read_bytes()
                        ).hexdigest(),
                    }
                )
            )
            model = PlanModel(
                id=target.id,
                revision=1,
                image_transform=ImageTransform(width=width, height=height),
                notes=[
                    f"Rectified from source {bid} using confirmed page proportions. Original plan and revisions retained."
                ],
            )
            model.scale.reference = reference
            model = PlanModel.model_validate(model.dump())
            s.add(target)
            s.add(PlanRevision(blueprint_id=target.id, revision=1, model=model.dump()))
            s.commit()
        except Exception:
            shutil.rmtree(folder)
            raise
        return {
            "id": target.id,
            "sourceToRectified": matrix.tolist(),
            "referencePreserved": reference is not None,
        }
