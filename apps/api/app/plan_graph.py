"""CanonicalPlan v1: explicit shared junctions, wall edges and anchored openings.

An additive graph model. Legacy Layout.geometry remains the public 2D/3D
format until the migration is benchmarked and explicitly approved.
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field
from .geometry import Pt, Room, Opening


class PlanNode(BaseModel):
    id: str
    point: Pt
    evidence_ids: list[str] = Field(default_factory=list)


class PlanWall(BaseModel):
    id: str
    start_node_id: str
    end_node_id: str
    thickness_m: float = Field(default=0.15, gt=0, le=2)
    height_m: float = Field(default=2.8, gt=0, le=20)
    source_wall_id: str | None = None
    inferred: bool = True
    evidence_ids: list[str] = Field(default_factory=list)


class PlanOpening(BaseModel):
    id: str
    wall_id: str
    kind: Literal['door', 'window']
    offset_m: float = Field(ge=0)
    width_m: float = Field(gt=0)
    height_m: float = Field(gt=0)
    sill_m: float = Field(default=0., ge=0)
    source_detection_id: str | None = None
    reviewed: bool = False
    inferred: bool = True


class BoundaryEdge(BaseModel):
    wall_id: str
    forward: bool = True


class PlanRoom(BaseModel):
    id: str
    boundary: list[BoundaryEdge] = Field(min_length=3)
    label: str = 'Proposed room'
    verified: bool = False
    evidence_ids: list[str] = Field(default_factory=list)


class CanonicalPlan(BaseModel):
    schema_version: Literal[1] = 1
    width_px: int = Field(gt=0)
    height_px: int = Field(gt=0)
    px_per_meter: float | None = Field(default=None, gt=0)
    scale_source: Literal['unknown', 'provisional_auto', 'user_confirmed'] = 'unknown'
    nodes: list[PlanNode] = Field(default_factory=list)
    walls: list[PlanWall] = Field(default_factory=list)
    openings: list[PlanOpening] = Field(default_factory=list)
    rooms: list[PlanRoom] = Field(default_factory=list)
    # Keep legacy evidence if it cannot yet be represented without guessing.
    pending_openings: list[Opening] = Field(default_factory=list)
    legacy_rooms: list[Room] = Field(default_factory=list)
    provenance: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
