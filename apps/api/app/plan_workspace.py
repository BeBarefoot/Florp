"""Pixel-space authoritative editor; metric values are derived, never guessed."""

from __future__ import annotations
import asyncio, json, math, sys, tempfile, os, signal
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field, ConfigDict, model_validator
from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union, polygonize
from .models import Blueprint, Layout, WorkspaceRevision
from .deterministic_blueprint.schema import CalibrationReference

router = APIRouter()


class Point(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    x: float
    y: float


class Segment(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    id: str = Field(max_length=120)
    kind: Literal["wall", "door", "window"] = "wall"
    start: Point
    end: Point
    thickness_px: float = Field(default=8, gt=0, le=1000)
    host_id: str | None = None
    exterior: bool | None = None
    material: Literal["block", "concrete"] = "block"
    reviewed: bool = False
    uncertain: bool = False
    height_m: float = Field(default=2.8, gt=0, le=20)
    sill_m: float = Field(default=0, ge=0, le=10)


class Document(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    objects: list[Segment] = Field(default_factory=list, max_length=5000)
    reference: CalibrationReference | None = None
    warnings: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def valid(self):
        ids = set()
        for item in self.objects:
            if item.id in ids:
                raise ValueError("Duplicate object ID")
            ids.add(item.id)
            if math.hypot(item.end.x - item.start.x, item.end.y - item.start.y) < 2:
                raise ValueError("Object is too short")
            for p in (item.start, item.end):
                if not 0 <= p.x <= self.width or not 0 <= p.y <= self.height:
                    raise ValueError("Object exceeds source image")
        walls = {o.id: o for o in self.objects if o.kind == "wall"}
        for o in self.objects:
            if o.host_id and o.host_id not in walls:
                raise ValueError("Opening host does not exist")
            if o.kind == "wall" and o.host_id:
                raise ValueError("Wall cannot have an opening host")
            if o.host_id:
                host = walls[o.host_id]
                if o.sill_m + o.height_m > host.height_m:
                    raise ValueError("Opening exceeds host wall height")
                line = LineString(
                    [(host.start.x, host.start.y), (host.end.x, host.end.y)]
                )
                from shapely.geometry import Point as ShapePoint

                if any(
                    line.distance(ShapePoint(p.x, p.y)) > max(2, host.thickness_px)
                    for p in (o.start, o.end)
                ):
                    raise ValueError("Opening must lie along its host wall")
        if self.reference:
            for x, y in (self.reference.start, self.reference.end):
                if not 0 <= x <= self.width or not 0 <= y <= self.height:
                    raise ValueError("Reference exceeds source image")
            if math.dist(self.reference.start, self.reference.end) < 5:
                raise ValueError("Use a longer measurement reference")
        return self


class Save(BaseModel):
    expected_version: int = Field(ge=0)
    document: Document


def get_engine():
    from .main import engine

    return engine


def scale(d):
    return (
        math.dist(d.reference.start, d.reference.end) / (d.reference.length_cm / 100)
        if d.reference
        else None
    )


def footprint(o):
    return LineString([(o.start.x, o.start.y), (o.end.x, o.end.y)]).buffer(
        o.thickness_px / 2, cap_style=2, join_style=2
    )


def derived(d: Document):
    ppm = scale(d)
    walls = [o for o in d.objects if o.kind == "wall"]
    solid = unary_union([footprint(o) for o in walls])
    network = unary_union(
        [LineString([(o.start.x, o.start.y), (o.end.x, o.end.y)]) for o in walls]
    )
    rooms = []
    cells = list(polygonize(network))
    for room in cells:
        clear = room.difference(solid)
        parts = list(clear.geoms) if hasattr(clear, "geoms") else [clear]
        for p in parts:
            if isinstance(p, Polygon) and p.area > 16:
                coords = [{"x": x, "y": y} for x, y in list(p.exterior.coords)[:-1]]
                rooms.append(
                    {
                        "id": f"room-{len(rooms)}",
                        "points": coords,
                        "area_m2": p.area / ppm**2 if ppm else None,
                        "width_m": (p.bounds[2] - p.bounds[0]) / ppm
                        if ppm
                        and len(coords) == 4
                        and abs(
                            p.area
                            - (p.bounds[2] - p.bounds[0]) * (p.bounds[3] - p.bounds[1])
                        )
                        < 1
                        else None,
                        "depth_m": (p.bounds[3] - p.bounds[1]) / ppm
                        if ppm
                        and len(coords) == 4
                        and abs(
                            p.area
                            - (p.bounds[2] - p.bounds[0]) * (p.bounds[3] - p.bounds[1])
                        )
                        < 1
                        else None,
                    }
                )
    enclosed = unary_union(cells)
    bounded = (
        bool(cells)
        and solid.difference(
            enclosed.buffer(max((o.thickness_px for o in walls), default=0))
        ).area
        < 1
    )
    return {
        "footprint_area_m2": unary_union([enclosed, solid]).area / ppm**2
        if bounded and ppm
        else None,
        "px_per_meter": ppm,
        "rooms": rooms,
        "bounds_px": list(solid.bounds) if not solid.is_empty else None,
        "margin_px": 0.5 * ppm if ppm else None,
    }


def legacy(bp, row):
    g = row.geometry if row else {}
    objects = []
    ppm = g.get("px_per_meter")
    for w in g.get("walls", []):
        if (
            g.get("warnings")
            and any("Starter geometry" in s for s in g["warnings"])
            and w["id"] in ["w0", "w1", "w2", "w3"]
        ):
            continue
        objects.append(
            Segment(
                id=w["id"],
                start=w["start"],
                end=w["end"],
                thickness_px=w.get("thickness_m", 0.15) * (ppm or 60),
                height_m=w.get("height_m", 2.8),
            )
        )
    walls = {o.id: o for o in objects}
    for op in g.get("openings", []):
        host = walls.get(op["wall_id"])
        if not host or not ppm:
            continue
        dx = host.end.x - host.start.x
        dy = host.end.y - host.start.y
        length = math.hypot(dx, dy)
        a = op["offset_m"] * ppm / length
        b = (op["offset_m"] + op["width_m"]) * ppm / length
        objects.append(
            Segment(
                id=op["id"],
                kind=op["kind"],
                start=Point(x=host.start.x + dx * a, y=host.start.y + dy * a),
                end=Point(x=host.start.x + dx * b, y=host.start.y + dy * b),
                host_id=host.id,
                thickness_px=host.thickness_px,
                height_m=op["height_m"],
                sill_m=op["sill_m"],
            )
        )
    reference = None
    if ppm and g.get("scale_source") == "user_confirmed":
        reference = CalibrationReference(
            start=(0, 0),
            end=(min(bp.width, ppm), 0),
            length_cm=min(bp.width, ppm) / ppm * 100,
        )
    return Document(
        width=bp.width,
        height=bp.height,
        objects=objects,
        reference=reference,
        warnings=["Imported saved layout; historical versions remain available."]
        if objects
        else [],
    )


def latest(s, bid):
    return s.exec(
        select(WorkspaceRevision)
        .where(WorkspaceRevision.blueprint_id == bid)
        .order_by(WorkspaceRevision.version.desc())
    ).first()


def response(row):
    d = Document.model_validate(row.document)
    return {"version": row.version, "document": d.model_dump(), "derived": derived(d)}


@router.get("/blueprints/{bid}/workspace")
def load(bid: str):
    with Session(get_engine()) as s:
        bp = s.get(Blueprint, bid)
        if not bp:
            raise HTTPException(404, "Plan not found")
        row = latest(s, bid)
        if row:
            return response(row)
        old = s.exec(
            select(Layout)
            .where(Layout.blueprint_id == bid)
            .order_by(Layout.version.desc())
        ).first()
        d = legacy(bp, old)
        return {"version": 0, "document": d.model_dump(), "derived": derived(d)}


@router.put("/blueprints/{bid}/workspace")
def save(bid: str, body: Save):
    with Session(get_engine()) as s:
        bp = s.get(Blueprint, bid)
        if not bp:
            raise HTTPException(404, "Plan not found")
        if (body.document.width, body.document.height) != (bp.width, bp.height):
            raise HTTPException(422, "Source dimensions changed")
        row = latest(s, bid)
        version = row.version if row else 0
        if version != body.expected_version:
            raise HTTPException(
                409,
                "A newer revision exists. Reload before saving; local changes are retained.",
            )
        row = WorkspaceRevision(
            blueprint_id=bid, version=version + 1, document=body.document.model_dump()
        )
        s.add(row)
        try:
            s.commit()
        except IntegrityError:
            raise HTTPException(409, "Revision changed; reload before saving")
        return response(row)


@router.post("/blueprints/{bid}/workspace/extract")
async def extract(bid: str, expected_version: int = 0):
    with Session(get_engine()) as s:
        bp = s.get(Blueprint, bid)
        if not bp:
            raise HTTPException(404, "Plan not found")
        current = latest(s, bid)
        if (current.version if current else 0) != expected_version:
            raise HTTPException(409, "Plan changed before extraction")
        path = bp.preview_path
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "result.json"
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
            env=env,
            start_new_session=True,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, error = await asyncio.wait_for(proc.communicate(), 20)
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
            from .config import settings
            if settings.workspace_semantic_source or settings.workspace_semantic_weights:
                raise HTTPException(
                    503,
                    "Local semantic evaluation failed. Check the trusted source, checkpoint, optional runtime and device configuration. Saved geometry is unchanged.",
                )
            raise HTTPException(
                422,
                "Unable to extract supported walls. Try a clearer, flat scan or add a wall directly.",
            )
        d = Document.model_validate_json(output.read_bytes())
    # Re-extraction never overwrites edits or scale; return a proposal for explicit replacement.
    with Session(get_engine()) as s:
        current = latest(s, bid)
        if (current.version if current else 0) != expected_version:
            raise HTTPException(
                409, "Plan changed during extraction; saved edits retained"
            )
    return {"document": d.model_dump(), "derived": derived(d)}


@router.get("/blueprints/{bid}/workspace/export")
def export(bid: str):
    payload = load(bid)
    d = Document.model_validate(payload["document"])
    ppm = scale(d)
    if not ppm:
        raise HTTPException(422, "Set one known measurement before metric export")
    if any(o.kind != "wall" and not o.host_id for o in d.objects):
        raise HTTPException(
            422,
            "An opening needs a host wall. Review its finding before exporting geometry.",
        )
    from .deterministic_blueprint.export import normalize_metric, png, svg, dxf, bundle

    layers = {
        name: unary_union(
            [
                footprint(o)
                for o in d.objects
                if o.kind == "wall"
                and (
                    o.material == "concrete"
                    if name == "LAYER_MAMAD_CONCRETE"
                    else o.material != "concrete"
                    and (
                        o.exterior is True
                        if name == "LAYER_WALLS_EXTERIOR"
                        else o.exterior is not True
                    )
                )
            ]
        )
        for name in [
            "LAYER_WALLS_EXTERIOR",
            "LAYER_WALLS_INTERIOR",
            "LAYER_MAMAD_CONCRETE",
        ]
    }
    if all(g.is_empty for g in layers.values()):
        raise HTTPException(422, "No walls to export")
    openings = unary_union(
        [footprint(o) for o in d.objects if o.kind != "wall" and o.host_id]
    )
    layers = {k: g.difference(openings) for k, g in layers.items()}
    layers, bounds, report = normalize_metric(layers, ppm / 100)
    raster, meta = png(layers, bounds, 100)
    report.update(
        {
            "revision": payload["version"],
            "reference": d.reference.model_dump(),
            "raster": meta,
            "workspace": d.model_dump(),
            "classification": "Walls have not been material/exterior classified",
        }
    )
    return Response(
        bundle(
            layers,
            bounds,
            report,
            raster,
            svg(layers, bounds, 100),
            dxf(layers, bounds),
        ),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="florp-plan.zip"'},
    )


@router.get("/blueprints/{bid}/info")
def info(bid: str):
    with Session(get_engine()) as s:
        bp = s.get(Blueprint, bid)
        if not bp:
            raise HTTPException(404, "Plan not found")
        return {
            "id": bp.id,
            "project_id": bp.project_id,
            "filename": bp.filename,
            "width": bp.width,
            "height": bp.height,
        }


@router.get("/blueprints/{bid}/workspace/history")
def history(bid: str):
    with Session(get_engine()) as s:
        return [
            {"version": r.version, "created_at": r.created_at, "document": r.document}
            for r in s.exec(
                select(WorkspaceRevision)
                .where(WorkspaceRevision.blueprint_id == bid)
                .order_by(WorkspaceRevision.version.desc())
            ).all()
        ]


class Rectification(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    corners: list[tuple[float, float]] = Field(min_length=4, max_length=4)
    page_aspect_ratio: float = Field(ge=0.1, le=10)
    expected_version: int = Field(ge=0)


@router.post("/blueprints/{bid}/workspace/straighten")
def straighten(bid: str, body: Rectification):
    """Create a new rectified source; preserve original plan and every revision."""
    import cv2, numpy as np, shutil, hashlib
    from PIL import Image
    from .config import settings
    from .deterministic_blueprint.preprocess import decode, order_quad, transform_points

    with Session(get_engine()) as s:
        source = s.get(Blueprint, bid)
        if not source:
            raise HTTPException(404, "Source not found")
        current = latest(s, bid)
        if (current.version if current else 0) != body.expected_version:
            raise HTTPException(409, "Save/reload the source before straightening")
        initial = Document.model_validate(current.document) if current else None
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
            raise HTTPException(
                422, "Select four corners enclosing the sheet, inside the image"
            )
        vectors = np.roll(q, -1, axis=0) - q
        width = (np.linalg.norm(vectors[0]) + np.linalg.norm(vectors[2])) / 2
        height = width / body.page_aspect_ratio
        factor = min(1, 4000 / max(width, height))
        width = max(16, round(width * factor))
        height = max(16, round(height * factor))
        matrix = cv2.getPerspectiveTransform(
            q,
            np.float32(
                [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]]
            ),
        )
        rectified = cv2.warpPerspective(
            image, matrix, (width, height), borderValue=(255, 255, 255)
        )
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
        if initial and initial.reference:
            pts = transform_points(
                [initial.reference.start, initial.reference.end], matrix
            )
            if (
                np.all(pts >= 0)
                and np.all(pts[:, 0] <= width - 1)
                and np.all(pts[:, 1] <= height - 1)
                and np.linalg.norm(pts[1] - pts[0]) >= 5
            ):
                reference = CalibrationReference(
                    start=tuple(pts[0]),
                    end=tuple(pts[1]),
                    length_cm=initial.reference.length_cm,
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
            d = Document(
                width=width,
                height=height,
                reference=reference,
                warnings=[
                    "Rectified from source "
                    + bid
                    + " using confirmed page proportions. Original plan and revisions retained."
                ],
            )
            s.add(target)
            s.add(
                WorkspaceRevision(
                    blueprint_id=target.id, version=1, document=d.model_dump()
                )
            )
            s.commit()
        except Exception:
            shutil.rmtree(folder)
            raise
        return {
            "id": target.id,
            "source_to_rectified": matrix.tolist(),
            "reference_preserved": reference is not None,
        }
