"""Human architecture review is revision-specific, separate from calibration."""
import hashlib
import json
from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from shapely.geometry import LineString, Point, Polygon
from shapely.strtree import STRtree
from sqlmodel import Session, select
from .models import PlanReview, PlanRevision
from .plan_api import blueprint, get_engine, latest
from .plan_model import PlanModel, wall_length

router = APIRouter(prefix='/blueprints/{bid}/plan/review')


def fingerprint(model):
    return hashlib.sha256(json.dumps(model, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def blockers(model):
    issues = []
    if not model.scale.reference:
        issues.append('Confirm one known measurement before review.')
    if not model.walls or not model.rooms:
        issues.append('At least one enclosed room is required; check wall connections.')
    if any(o.status == 'proposed' for o in model.openings):
        issues.append('Approve or reject every proposed door and window.')
    if any(wall_length(model, w) < 1 for w in model.walls):
        issues.append('Remove walls shorter than one source pixel.')
    nodes = {n.id:n for n in model.nodes}
    lines = [LineString([(nodes[w.a].x, nodes[w.a].y), (nodes[w.b].x, nodes[w.b].y)]) for w in model.walls]
    tree = STRtree(lines)
    crossing = False
    for i, line in enumerate(lines):
        for j in tree.query(line, predicate='intersects'):
            if j <= i:
                continue
            a, b = model.walls[i], model.walls[j]
            intersection = line.intersection(lines[j])
            shared = {a.a, a.b} & {b.a, b.b}
            if not (intersection.geom_type == 'Point' and any(
                intersection.distance(Point(nodes[n].x, nodes[n].y)) < 1e-6 for n in shared)):
                crossing = True
                break
        if crossing:
            break
    if crossing:
        issues.append('Resolve crossing or overlapping walls with shared junctions.')
    spans = {}
    for o in model.openings:
        if o.status == 'confirmed':
            spans.setdefault(o.host_wall_id, []).append((o.offset_px, o.offset_px + o.width_px))
    if any(any(b[0] < a[1] - .5 for a, b in zip(sorted(group), sorted(group)[1:])) for group in spans.values()):
        issues.append('Resolve overlapping confirmed openings on the same wall.')
    if any(not Polygon([(p.x, p.y) for p in r.polygon]).is_valid or r.area_px2 <= 0 for r in model.rooms):
        issues.append('Resolve invalid room boundaries.')
    if any(r.needs_semantic_review for r in model.rooms):
        issues.append('Review room labels and heights after the split or merge.')
    return issues


def review_info(session, row):
    if row is None:
        return {'revision': 0, 'status': 'draft', 'blockers': ['Save a plan first.'], 'elevations': None, 'reviewedAt': None}
    issues = blockers(PlanModel.model_validate(row.model))
    receipt = session.exec(select(PlanReview).where(PlanReview.blueprint_id == row.blueprint_id,
        PlanReview.revision == row.revision).order_by(PlanReview.created_at.desc(), PlanReview.id.desc())).first()
    accepted = bool(receipt and receipt.accepted and receipt.model_hash == fingerprint(row.model) and not issues)
    return {'revision': row.revision, 'status': 'reviewed' if accepted else 'draft', 'blockers': issues,
            'elevations': receipt.elevations if accepted else None,
            'reviewedAt': receipt.created_at.isoformat() if accepted else None,
            'modelHash': fingerprint(row.model)}


@router.get('')
def get_review(bid: str, revision: int | None = None):
    with Session(get_engine()) as session:
        blueprint(session, bid)
        row = latest(session, bid) if revision is None else session.exec(select(PlanRevision).where(
            PlanRevision.blueprint_id == bid, PlanRevision.revision == revision)).first()
        if revision is not None and row is None:
            raise HTTPException(404, 'Plan revision not found')
        return review_info(session, row)


class Review(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(gt=0)
    topology: Literal[True]
    openings: Literal[True]
    scale: Literal[True]
    elevations: Literal['confirmed', 'assumed']


class Reopen(BaseModel):
    revision: int = Field(gt=0)


def record(bid, revision, accepted, elevations='assumed'):
    with Session(get_engine()) as session:
        blueprint(session, bid)
        row = latest(session, bid)
        if row is None or row.revision != revision:
            raise HTTPException(409, 'The plan changed. Reload and review the current saved revision.')
        if accepted:
            issues = blockers(PlanModel.model_validate(row.model))
            if issues:
                raise HTTPException(422, {'message': 'Resolve these issues before recording review.', 'issues': issues})
        session.add(PlanReview(blueprint_id=bid, revision=revision, model_hash=fingerprint(row.model),
                               accepted=accepted, elevations=elevations))
        session.commit()
        return review_info(session, row)


@router.post('')
def accept(bid: str, body: Review):
    return record(bid, body.revision, True, body.elevations)


@router.delete('')
def reopen(bid: str, body: Reopen):
    return record(bid, body.revision, False)
