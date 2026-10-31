"""Raw extractor output types (pixel space). The editable model is plan_model.PlanModel."""

from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator
import math
from shapely.geometry import LineString
from .deterministic_blueprint.schema import CalibrationReference



class Point(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    x: float
    y: float


class Segment(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    id: str = Field(max_length=120)
    kind: Literal["wall", "door", "window", "garage"] = "wall"
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
    confidence: float | None = Field(default=None, ge=0, le=1)
    boundary_supported: bool = False  # two observed faces; protect short photo piers/returns
    leaf: Point | None = None  # unit vector from the hinge across the wall: where a door's leaf opens


class Document(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    objects: list[Segment] = Field(default_factory=list, max_length=5000)
    reference: CalibrationReference | None = None
    envelope: list[Point] | None = None
    passages: list[Point] = Field(default_factory=list, max_length=500)
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


def footprint(o):
    return LineString([(o.start.x, o.start.y), (o.end.x, o.end.y)]).buffer(
        o.thickness_px / 2, cap_style=2, join_style=2
    )
