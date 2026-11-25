"""PlanModel v2: the single authoritative plan behind 2D editing, calibration and 3D.

Geometry is stored in source-image pixels only. Metric values are always
derived as ``px * meters_per_pixel``; calibration never rewrites coordinates.
"""

from __future__ import annotations
import math
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator
from pydantic.alias_generators import to_camel

from .gardens import Garden

FindingCategory = Literal[
    "opening_needs_approval",
    "open_wall_end",
    "suggested_closure",
    "low_confidence_wall",
    "unclosed_region",
    "pruned_fragments",
    "merged_duplicates",
    "open_passage",
]


class Base(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        allow_inf_nan=False,
        extra="forbid",
    )


class Pt(Base):
    x: float
    y: float


class ImageTransform(Base):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    rotation: float = 0


class Reference(Base):
    p1: Pt
    p2: Pt
    length_meters: float = Field(gt=0, le=1000)


class ScaleProposal(Base):
    reference: Reference
    check_reference: Reference
    evidence_count: int = Field(ge=3)


class Scale(Base):
    meters_per_pixel: float | None = None
    reference: Reference | None = None
    check_reference: Reference | None = None
    proposal: ScaleProposal | None = None

    @model_serializer(mode="wrap")
    def serialize_reference_check(self, serialize):
        data = serialize(self)
        if self.check_reference is None:
            data.pop("check_reference", None)
            data.pop("checkReference", None)
        if self.proposal is None:
            data.pop("proposal", None)
        return data


class Node(Base):
    id: str = Field(max_length=120)
    x: float
    y: float


class Wall(Base):
    id: str = Field(max_length=120)
    a: str
    b: str
    thickness_px: float = Field(gt=0, le=1000)
    height_m: float = Field(default=2.8, gt=0, le=20)
    material: Literal["block", "concrete"] = "block"
    exterior: bool | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    source: Literal["extracted", "user"] = "extracted"


class WindowFrame(Base):
    material: Literal["wood", "aluminium", "vinyl"]
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    width_m: float = Field(ge=0.02, le=0.15)
    panes: Literal[1, 2] = 1


class Opening(Base):
    id: str = Field(max_length=120)
    kind: Literal["door", "window", "garage"]
    host_wall_id: str | None = None
    offset_px: float = 0
    width_px: float = Field(default=0, ge=0)
    span: tuple[Pt, Pt] | None = None
    height_m: float = Field(default=2.1, gt=0, le=20)
    sill_m: float = Field(default=0, ge=0, le=10)
    swing: Literal["left", "right"] | None = None
    hinge: Literal["start", "end"] = "start"
    confidence: float = Field(default=1.0, ge=0, le=1)
    status: Literal["proposed", "confirmed", "rejected"] = "proposed"
    window_frame: WindowFrame | None = None


class RoomSymbol(Base):
    kind: Literal["car", "bed"]
    position: Pt


class Room(Base):
    id: str
    wall_ids: list[str] = Field(default_factory=list)
    polygon: list[Pt]
    area_px2: float = Field(ge=0)
    label: str | None = Field(default=None, max_length=80)
    room_type: Literal["bedroom", "garage", "bathroom", "kitchen", "corridor", "balcony", "other"] | None = None
    ceiling_height_m: float | None = Field(default=None, ge=1.8, le=8)
    needs_semantic_review: bool = False


class RoomZone(Base):
    id: str = Field(min_length=1, max_length=120)
    polygon: list[Pt] = Field(min_length=3, max_length=32)
    label: str | None = Field(default=None, max_length=80)
    room_type: Literal["bedroom", "garage", "bathroom", "kitchen", "corridor", "balcony", "other"] | None = None
    ceiling_height_m: float | None = Field(default=None, ge=1.8, le=8)


class Stair(Base):
    """Treads run from the start of a flight, or bottom to top for both directions."""
    id: str = Field(max_length=120)
    layout: Literal["l", "u"]
    treads: list[list[Pt]] = Field(min_length=3, max_length=80)
    rise_m: float = Field(default=0.17, ge=0.08, le=0.3)
    direction: Literal["up", "down", "both"] = "up"
    treads_below: int | None = Field(default=None, ge=1, le=78)

    @model_validator(mode="after")
    def validate_landing(self):
        if self.direction == "both" and (self.treads_below is None or self.treads_below >= len(self.treads) - 1):
            raise ValueError("Choose a landing with at least one tread above and below")
        return self


class ClosureEvidence(Base):
    start: Pt
    end: Pt
    thickness_px: float = Field(gt=0, le=1000)


class Finding(Base):
    closure: ClosureEvidence | None = None
    id: str
    category: FindingCategory
    severity: Literal["info", "warn"] = "warn"
    target_ids: list[str] = Field(default_factory=list)
    anchor: Pt
    count: int = Field(default=1, ge=1)
    message: str = ""


class PlanModel(Base):
    gardens: list[Garden] = Field(default_factory=list, max_length=12)
    schema_version: Literal[2] = 2
    id: str
    revision: int = Field(default=0, ge=0)
    image_transform: ImageTransform
    scale: Scale = Field(default_factory=Scale)
    nodes: list[Node] = Field(default_factory=list, max_length=20000)
    walls: list[Wall] = Field(default_factory=list, max_length=10000)
    openings: list[Opening] = Field(default_factory=list, max_length=5000)
    stairs: list[Stair] = Field(default_factory=list, max_length=32)
    room_symbols: list[RoomSymbol] = Field(default_factory=list, max_length=256)
    rooms: list[Room] = Field(default_factory=list)
    room_zones: list[RoomZone] = Field(default_factory=list, max_length=50)
    findings: list[Finding] = Field(default_factory=list)
    envelope: list[Pt] | None = None
    dismissed_findings: list[str] = Field(default_factory=list, max_length=5000)
    notes: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def valid(self):
        w, h = self.image_transform.width, self.image_transform.height
        nodes = {}
        for n in self.nodes:
            if n.id in nodes:
                raise ValueError("Duplicate node ID")
            if not (0 <= n.x <= w and 0 <= n.y <= h):
                raise ValueError("Node exceeds source image")
            nodes[n.id] = n
        walls = {}
        for wall in self.walls:
            if wall.id in walls:
                raise ValueError("Duplicate wall ID")
            if wall.a not in nodes or wall.b not in nodes:
                raise ValueError("Wall references a missing node")
            if wall.a == wall.b:
                raise ValueError("Wall must connect two distinct nodes")
            walls[wall.id] = wall
        ids = set()
        for o in self.openings:
            if o.id in ids or o.id in walls:
                raise ValueError("Duplicate opening ID")
            ids.add(o.id)
            if o.host_wall_id is None:
                if o.status == "confirmed":
                    raise ValueError("A confirmed opening needs a host wall")
                if o.span is None:
                    raise ValueError("An unhosted opening must keep its source span")
                continue
            host = walls.get(o.host_wall_id)
            if host is None:
                raise ValueError("Opening host does not exist")
            length = wall_length(self, host, nodes)
            if o.offset_px < -0.5 or o.offset_px + o.width_px > length + 0.5:
                raise ValueError("Opening exceeds its host wall")
            if o.width_px < 1:
                raise ValueError("Opening is too narrow")
            if o.sill_m + o.height_m > host.height_m + 1e-6:
                raise ValueError("Opening exceeds host wall height")
        for symbol in self.room_symbols:
            if not (0 <= symbol.position.x <= w and 0 <= symbol.position.y <= h):
                raise ValueError("Room symbol exceeds source image")
        for stair in self.stairs:
            if stair.id in ids or stair.id in walls:
                raise ValueError("Duplicate stair ID")
            ids.add(stair.id)
            for tread in stair.treads:
                if not 3 <= len(tread) <= 4 or any(not (0 <= p.x <= w and 0 <= p.y <= h) for p in tread):
                    raise ValueError("Invalid stair tread footprint")
                area = sum(a.x * b.y - b.x * a.y for a, b in zip(tread, tread[1:] + tread[:1]))
                if abs(area) < 2:
                    raise ValueError("Stair tread is too small")
                turns = [(b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x)
                         for a, b, c in zip(tread, tread[1:] + tread[:1], tread[2:] + tread[:2])]
                if not (min(turns) > 0 or max(turns) < 0):
                    raise ValueError("Stair treads must be convex")
        from shapely.geometry import Polygon
        zone_ids = set()
        for zone in self.room_zones:
            if zone.id in zone_ids or any(not (0 <= p.x <= w and 0 <= p.y <= h) for p in zone.polygon):
                raise ValueError("Invalid room zone position or ID")
            zone_ids.add(zone.id)
            poly = Polygon([(p.x, p.y) for p in zone.polygon])
            if not poly.is_valid or poly.area < 4:
                raise ValueError("Invalid room zone shape")
        def reference_pixels(ref):
            for p in (ref.p1, ref.p2):
                if not (0 <= p.x <= w and 0 <= p.y <= h):
                    raise ValueError("Reference exceeds source image")
            pixels = math.hypot(ref.p2.x - ref.p1.x, ref.p2.y - ref.p1.y)
            if pixels < 5:
                raise ValueError("Use a longer measurement reference")
            return pixels

        ref = self.scale.reference
        check = self.scale.check_reference
        proposal = self.scale.proposal
        if proposal:
            a, b = proposal.reference, proposal.check_reference
            a_scale, b_scale = a.length_meters / reference_pixels(a), b.length_meters / reference_pixels(b)
            def horizontal(line):
                return abs(line.p2.x - line.p1.x) > abs(line.p2.y - line.p1.y)
            if horizontal(a) == horizontal(b) or abs(a_scale / b_scale - 1) > .02 + 1e-9:
                raise ValueError("Scale proposals need agreeing horizontal and vertical spans")
        if check:
            if not ref:
                raise ValueError("Set the scale reference before adding a check")
            if (ref.p1, ref.p2) in ((check.p1, check.p2), (check.p2, check.p1)):
                raise ValueError("Check the scale using a different known distance")
            reference_pixels(check)
        if ref:
            pixels = reference_pixels(ref)
            self.scale.meters_per_pixel = ref.length_meters / pixels
        else:
            self.scale.meters_per_pixel = None
        return self

    def dump(self) -> dict:
        return self.model_dump(mode="json", by_alias=True)


def wall_length(model: PlanModel, wall: Wall, nodes: dict | None = None) -> float:
    nodes = nodes or {n.id: n for n in model.nodes}
    a, b = nodes[wall.a], nodes[wall.b]
    return math.hypot(b.x - a.x, b.y - a.y)
