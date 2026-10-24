from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, JSON
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
