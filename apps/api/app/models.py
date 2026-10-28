from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON, UniqueConstraint
from uuid import uuid4

def uid(): return str(uuid4())
def now(): return datetime.now(timezone.utc)
class Project(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    title: str
    created_at: datetime = Field(default_factory=now)
class Blueprint(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    project_id: str = Field(index=True, foreign_key='project.id')
    filename: str
    local_path: str
    preview_path: str
    width: int
    height: int
    created_at: datetime = Field(default_factory=now)
class Layout(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    blueprint_id: str = Field(index=True, foreign_key='blueprint.id')
    version: int = 1
    verified: bool = False
    geometry: dict = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime = Field(default_factory=now)
class Render(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    blueprint_id: str = Field(index=True, foreign_key='blueprint.id')
    layout_id: str
    camera: dict = Field(default_factory=dict, sa_type=JSON)
    prompt: str
    status: str = 'queued'
    image_path: Optional[str] = None
    error: Optional[str] = None
    provider_job_id: Optional[str] = None
    created_at: datetime = Field(default_factory=now)

class WallAnnotation(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    blueprint_id: str = Field(index=True, foreign_key='blueprint.id')
    candidate_key: str = Field(index=True)
    label: str
    coordinates: dict = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime = Field(default_factory=now)

class ModelWallCorrection(SQLModel, table=True):
    id: str = Field(default_factory=uid, primary_key=True)
    blueprint_id: str = Field(index=True, foreign_key='blueprint.id')
    model_wall_id: str = Field(index=True)
    action: str
    original: dict = Field(default_factory=dict, sa_type=JSON)
    corrected: dict = Field(default_factory=dict, sa_type=JSON)
    layout_version: int
    created_at: datetime = Field(default_factory=now)

class FusionCandidateReview(SQLModel,table=True):
    """Append-only human decisions tied to the original image and model proposal."""
    id: str = Field(default_factory=uid,primary_key=True)
    blueprint_id: str = Field(index=True,foreign_key='blueprint.id')
    preview_sha256: str = Field(index=True)
    candidate_id: str = Field(index=True)
    category: str
    decision: str
    candidate: dict = Field(default_factory=dict,sa_type=JSON)
    input_manifest: dict = Field(default_factory=dict,sa_type=JSON)
    created_at: datetime = Field(default_factory=now)

class ExtractionEvaluation(SQLModel,table=True):
    """Immutable source-bound baseline + optionally reviewed reference and metrics."""
    id: str = Field(default_factory=uid,primary_key=True)
    blueprint_id: str = Field(index=True,foreign_key='blueprint.id')
    image_sha256: str = Field(index=True)
    provider: str
    base_layout_version: int
    baseline: dict = Field(default_factory=dict,sa_type=JSON)
    reference: dict = Field(default_factory=dict,sa_type=JSON)
    metrics: dict = Field(default_factory=dict,sa_type=JSON)
    correction_seconds: Optional[int] = None
    notes: str = ''
    status: str = 'baseline'
    created_at: datetime = Field(default_factory=now)
    completed_at: Optional[datetime] = None

class PlanGraphRevision(SQLModel, table=True):
    """Append-only canonical plan snapshots; never overwrite Layout.geometry."""
    __table_args__ = (UniqueConstraint('blueprint_id','version',name='uq_plan_revision_blueprint_version'),)
    id: str = Field(default_factory=uid,primary_key=True)
    blueprint_id: str = Field(index=True,foreign_key='blueprint.id')
    source_layout_id: str
    source_layout_version: int
    version: int
    parent_revision_id: Optional[str] = None
    operation: dict = Field(default_factory=dict,sa_type=JSON)
    graph: dict = Field(default_factory=dict,sa_type=JSON)
    created_at: datetime = Field(default_factory=now)
