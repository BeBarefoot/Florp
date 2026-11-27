"""Save an independent design copy and compare it with its recorded baseline."""
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from .models import Blueprint, DesignVariant, PlanRevision, SceneRevision
from .plan_api import blueprint, get_engine, latest
from .plan_derive import derive
from .plan_model import PlanModel
from .scene_api import Data, Scene, current

router = APIRouter()


class ClosetMetrics(Data):
    passage: float = Field(gt=0, le=10)
    storage_depth: float = Field(gt=0, le=8)
    moved: int = Field(ge=0, le=100)


class CreateVariant(Data):
    request_id: UUID
    title: str = Field(min_length=1, max_length=80)
    plan_revision: int = Field(gt=0)
    scene_revision: int = Field(ge=0)
    metrics: ClosetMetrics
    plan: PlanModel
    scene: Scene


def summary(row):
    return {"id": row.blueprint_id, "sourceId": row.source_id, "title": row.title,
            "planRevision": row.plan_revision, "sceneRevision": row.scene_revision, "metrics": row.metrics}


@router.get("/blueprints/{bid}/variants")
def list_variants(bid: str):
    with Session(get_engine()) as session:
        blueprint(session, bid)
        return [summary(row) for row in session.exec(
            select(DesignVariant).where(DesignVariant.source_id == bid).order_by(DesignVariant.title, DesignVariant.blueprint_id)
        )]


@router.post("/blueprints/{bid}/variants")
def create_variant(bid: str, body: CreateVariant):
    variant_id = str(body.request_id)
    with Session(get_engine()) as session:
        source = blueprint(session, bid)
        existing = session.get(DesignVariant, variant_id)
        if existing and existing.source_id == bid:
            return summary(existing)
        plan = latest(session, bid)
        scene = current(session, bid)
        if not plan or plan.revision != body.plan_revision or (scene.revision if scene else 0) != body.scene_revision:
            raise HTTPException(409, "The baseline changed. Reload it before saving a variant.")
        if scene and scene.plan_revision != plan.revision:
            raise HTTPException(409, "Review the baseline scene against its current plan first.")
        if not body.plan.scale.reference or (body.plan.image_transform.width, body.plan.image_transform.height) != (source.width, source.height):
            raise HTTPException(422, "The variant needs a measured plan in the original drawing coordinates.")
        baseline = PlanModel.model_validate(plan.model)
        copy = derive(body.plan, identity_source=baseline.rooms).model_copy(update={"id": variant_id, "revision": 1})
        if not copy.walls:
            raise HTTPException(422, "The variant needs walls.")
        if len({obj.id for obj in body.scene.objects}) != len(body.scene.objects) or any(
            not (0 <= obj.position.x <= source.width and 0 <= obj.position.y <= source.height) for obj in body.scene.objects
        ):
            raise HTTPException(422, "Variant furniture positions or IDs are invalid.")
        row = DesignVariant(blueprint_id=variant_id, source_id=bid, title=body.title,
                            plan_revision=plan.revision, scene_revision=scene.revision if scene else 0,
                            metrics=body.metrics.model_dump(by_alias=True))
        # Source scans are immutable. Share their files while keeping editable data independent.
        session.add(Blueprint(id=variant_id, project_id=source.project_id, filename=body.title,
                              local_path=source.local_path, preview_path=source.preview_path,
                              width=source.width, height=source.height))
        session.add(PlanRevision(blueprint_id=variant_id, revision=1, model=copy.dump()))
        session.add(SceneRevision(blueprint_id=variant_id, revision=1, plan_revision=1, config=body.scene.model_dump(by_alias=True)))
        session.add(row)
        try:
            session.commit()
        except IntegrityError as exc:
            session.rollback()
            existing = session.get(DesignVariant, variant_id)
            if existing and existing.source_id == bid:
                return summary(existing)
            raise HTTPException(409, "The variant could not be saved with this ID.") from exc
        return summary(row)


@router.get("/design-variants/{vid}")
def compare_variant(vid: str):
    with Session(get_engine()) as session:
        row = session.get(DesignVariant, vid)
        if not row:
            raise HTTPException(404, "Design variant not found.")
        baseline = session.exec(select(PlanRevision).where(
            PlanRevision.blueprint_id == row.source_id, PlanRevision.revision == row.plan_revision)).first()
        old_scene = session.exec(select(SceneRevision).where(
            SceneRevision.blueprint_id == row.source_id, SceneRevision.revision == row.scene_revision)).first()
        proposal = latest(session, vid)
        new_scene = current(session, vid)
        if not baseline or not proposal:
            raise HTTPException(404, "An underlying plan revision is missing.")
        return {**summary(row),
                "baseline": {"plan": baseline.model, "scene": old_scene.config if old_scene else Scene().model_dump(by_alias=True)},
                "variant": {"plan": proposal.model, "scene": new_scene.config if new_scene else Scene().model_dump(by_alias=True)}}
