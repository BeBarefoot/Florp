import io, os, shutil
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlmodel import SQLModel, Session, create_engine, select
from pydantic import BaseModel
from PIL import Image
import fitz
from .config import settings
from .models import Project, Blueprint, Layout, Render, WallAnnotation
from .geometry import Geometry, fallback_geometry, validate_geometry
from .providers import extract_geometry, ProviderUnavailable, ProviderAuthenticationError
from .evidence import inspect_plan
from .reconcile import reconcile
from .geometry import Wall, Pt

Path(settings.storage_path).mkdir(parents=True,exist_ok=True)
if settings.database_url.startswith('sqlite:///'):
    Path(settings.database_url.removeprefix('sqlite:///')).parent.mkdir(parents=True,exist_ok=True)
engine=create_engine(settings.database_url,connect_args={'check_same_thread':False} if settings.database_url.startswith('sqlite') else {})
SQLModel.metadata.create_all(engine)
app=FastAPI(title='Florp API',version='0.1.0')
app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origins.split(','),allow_credentials=True,allow_methods=['*'],allow_headers=['*'])

@app.get('/health')
def health():return {'ok':True,'vision_configured':bool(settings.llm_api_key),'image_configured':bool(settings.image_api_key)}
class CreateProject(BaseModel): title:str
@app.post('/projects',response_model=Project)
def create_project(body:CreateProject):
    p=Project(title=body.title.strip() or 'Untitled')
    with Session(engine) as s:s.add(p);s.commit();s.refresh(p)
    return p
@app.get('/projects',response_model=list[Project])
def projects():
    with Session(engine) as s:return list(s.exec(select(Project).order_by(Project.created_at.desc())).all())
@app.get('/projects/{pid}/blueprints',response_model=list[Blueprint])
def blueprints(pid:str):
    with Session(engine) as s:return list(s.exec(select(Blueprint).where(Blueprint.project_id==pid)).all())
@app.post('/projects/{pid}/blueprints',response_model=Blueprint)
async def upload(pid:str,file:UploadFile=File(...)):
    with Session(engine) as s:
        if not s.get(Project,pid):raise HTTPException(404,'Project not found')
    contents=await file.read(settings.max_upload_mb*1024*1024+1)
    if len(contents)>settings.max_upload_mb*1024*1024:raise HTTPException(413,'Upload exceeds configured size')
    if contents.startswith(b'%PDF-'):
        try:
            pdf=fitz.open(stream=contents,filetype='pdf');page=pdf[0];pix=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False)
            image=Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
        except Exception:raise HTTPException(422,'Could not read PDF')
    else:
        try:image=Image.open(io.BytesIO(contents)).convert('RGB')
        except Exception:raise HTTPException(415,'Only PDF and common images are supported')
    if image.width*image.height>45_000_000:raise HTTPException(413,'Image pixel count too large')
    bp=Blueprint(project_id=pid,filename=(file.filename or 'plan')[:255],local_path='',preview_path='',width=image.width,height=image.height)
    folder=Path(settings.storage_path)/bp.id;folder.mkdir(parents=True,exist_ok=True)
    suffix='.pdf' if contents.startswith(b'%PDF-') else '.bin'
    raw=folder/('original'+suffix);raw.write_bytes(contents)
    preview=folder/'preview.png';image.save(preview)
    bp.local_path=str(raw);bp.preview_path=str(preview)
    layout=Layout(blueprint_id=bp.id,geometry=fallback_geometry(bp.width,bp.height).model_dump())
    with Session(engine) as s:s.add(bp);s.add(layout);s.commit();s.refresh(bp)
    return bp
@app.get('/blueprints/{bid}/preview')
def preview(bid:str):
    with Session(engine) as s:bp=s.get(Blueprint,bid)
    if not bp:raise HTTPException(404,'Not found')
    return FileResponse(bp.preview_path,media_type='image/png')
@app.get('/blueprints/{bid}/layout')
def get_layout(bid:str):
    with Session(engine) as s:
        row=s.exec(select(Layout).where(Layout.blueprint_id==bid).order_by(Layout.version.desc())).first()
        if not row:raise HTTPException(404,'No layout')
        return row
@app.get('/blueprints/{bid}/evidence')
def blueprint_evidence(bid:str):
    with Session(engine) as s:bp=s.get(Blueprint,bid)
    if not bp:raise HTTPException(404,'Not found')
    return inspect_plan(Path(bp.local_path),Path(bp.preview_path))

@app.post('/blueprints/{bid}/extract')
async def extract(bid:str):
    with Session(engine) as s:bp=s.get(Blueprint,bid)
    if not bp:raise HTTPException(404,'Not found')
    data=Path(bp.preview_path).read_bytes()
    try:g=await extract_geometry(data,'image/png',bp.width,bp.height)
    except ProviderAuthenticationError as e:raise HTTPException(424,str(e))
    except ProviderUnavailable as e:raise HTTPException(424,str(e))
    except Exception as e:raise HTTPException(502,f'Vision provider error: {type(e).__name__}: {e}')
    g=reconcile(g,inspect_plan(Path(bp.local_path),Path(bp.preview_path)))
    with Session(engine) as s:
        last=s.exec(select(Layout).where(Layout.blueprint_id==bid).order_by(Layout.version.desc())).first()
        row=Layout(blueprint_id=bid,version=(last.version+1 if last else 1),geometry=g.model_dump())
        s.add(row);s.commit();s.refresh(row)
        return row

class WallAnnotationInput(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    label: str

def annotation_key(c):
    return ':'.join(str(round(v,1)) for v in (c.x1,c.y1,c.x2,c.y2))

@app.get('/blueprints/{bid}/wall-annotations')
def get_annotations(bid:str):
    with Session(engine) as s:
        if not s.get(Blueprint,bid):raise HTTPException(404,'Blueprint not found')
        return list(s.exec(select(WallAnnotation).where(WallAnnotation.blueprint_id==bid)).all())

@app.post('/blueprints/{bid}/wall-annotations')
def label_wall(bid:str, body:WallAnnotationInput):
    if body.label not in ('wall','not_wall','unsure'):
        raise HTTPException(422,'label must be wall, not_wall, or unsure')
    from types import SimpleNamespace
    from math import isfinite
    vals=(body.x1,body.y1,body.x2,body.y2)
    if not all(isfinite(v) for v in vals):raise HTTPException(422,'Invalid coordinates')
    with Session(engine) as s:
        bp=s.get(Blueprint,bid)
        if not bp:raise HTTPException(404,'Blueprint not found')
        if not (0<=body.x1<=bp.width and 0<=body.x2<=bp.width and 0<=body.y1<=bp.height and 0<=body.y2<=bp.height):
            raise HTTPException(422,'Coordinates outside blueprint')
        key=annotation_key(body)
        previous=s.exec(select(WallAnnotation).where(WallAnnotation.blueprint_id==bid,WallAnnotation.candidate_key==key)).first()
        if previous:
            previous.label=body.label
            row=previous
        else:
            row=WallAnnotation(blueprint_id=bid,candidate_key=key,label=body.label,
              coordinates={'x1':body.x1,'y1':body.y1,'x2':body.x2,'y2':body.y2})
        s.add(row);s.commit();s.refresh(row)
        return row

@app.get('/blueprints/{bid}/training-export')
def training_export(bid:str):
    # Machine-readable annotations: positives/negatives plus human-drawn wall lines.
    with Session(engine) as s:
        bp=s.get(Blueprint,bid)
        if not bp:raise HTTPException(404,'Blueprint not found')
        annotations=list(s.exec(select(WallAnnotation).where(WallAnnotation.blueprint_id==bid)).all())
        layout=s.exec(select(Layout).where(Layout.blueprint_id==bid).order_by(Layout.version.desc())).first()
        walls=[w for w in Geometry.model_validate(layout.geometry).model_dump()['walls'] if w['id'].startswith('user-')] if layout else []
    return {'schema_version':1,'blueprint_id':bid,'image_width':bp.width,'image_height':bp.height,
      'annotations':[{'label':a.label,**a.coordinates} for a in annotations],
      'manually_drawn_walls':walls,'note':'Review labels before training; this is not a trained detector.'}

class AcceptCandidate(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float

@app.post('/blueprints/{bid}/wall-candidates/accept')
def accept_candidate(bid:str, body:AcceptCandidate):
    # The user explicitly promotes one suggestion to draft wall geometry.
    from uuid import uuid4
    from math import hypot
    with Session(engine) as s:
        bp=s.get(Blueprint,bid)
        if not bp:raise HTTPException(404,'Not found')
        current=s.exec(select(Layout).where(Layout.blueprint_id==bid).order_by(Layout.version.desc())).first()
        if not current:raise HTTPException(404,'No layout')
        evidence=inspect_plan(Path(bp.local_path),Path(bp.preview_path))
        if hypot(body.x2-body.x1,body.y2-body.y1)<5:raise HTTPException(422,'Candidate too short')
        for x,y in [(body.x1,body.y1),(body.x2,body.y2)]:
            if not (0<=x<=bp.width and 0<=y<=bp.height):raise HTTPException(422,'Candidate outside image')
        if not any(max(abs(body.x1-c.x1),abs(body.y1-c.y1),abs(body.x2-c.x2),abs(body.y2-c.y2))<3 for c in evidence.candidates):
            raise HTTPException(422,'Wall must match a currently detected suggestion')
        g=Geometry.model_validate(current.geometry).model_copy(deep=True)
        if any((hypot(w.start.x-body.x1,w.start.y-body.y1)<5 and hypot(w.end.x-body.x2,w.end.y-body.y2)<5) or
               (hypot(w.start.x-body.x2,w.start.y-body.y2)<5 and hypot(w.end.x-body.x1,w.end.y-body.y1)<5) for w in g.walls):
            raise HTTPException(409,'Wall already exists')
        g.walls.append(Wall(id='user-'+uuid4().hex[:12],start=Pt(x=body.x1,y=body.y1),end=Pt(x=body.x2,y=body.y2)))
        row=Layout(blueprint_id=bid,version=current.version+1,verified=False,geometry=g.model_dump())
        s.add(row);s.commit();s.refresh(row)
        return row

class SaveLayout(BaseModel):
    geometry:Geometry
    verified:bool=False
@app.post('/blueprints/{bid}/layout')
def save_layout(bid:str,body:SaveLayout):
    with Session(engine) as s:
        if not s.get(Blueprint,bid):raise HTTPException(404,'Not found')
        last=s.exec(select(Layout).where(Layout.blueprint_id==bid).order_by(Layout.version.desc())).first()
        warnings=validate_geometry(body.geometry)
        if body.verified and warnings:raise HTTPException(422,{'message':'Resolve validation issues before verification','issues':warnings})
        row=Layout(blueprint_id=bid,version=(last.version+1 if last else 1),verified=body.verified,geometry=body.geometry.model_dump())
        s.add(row);s.commit();s.refresh(row);return row
@app.get('/blueprints/{bid}/renders',response_model=list[Render])
def renders(bid:str):
    with Session(engine) as s:return list(s.exec(select(Render).where(Render.blueprint_id==bid).order_by(Render.created_at.desc())).all())
class RenderRequest(BaseModel):
    layout_id:str
    prompt:str
    camera:dict
@app.post('/blueprints/{bid}/renders')
def request_render(bid:str,body:RenderRequest):
    # Image generation requires a client-produced depth map; the API will not fabricate one.
    raise HTTPException(501,'Depth capture and render submission are scheduled for the next milestone; no synthetic render is generated.')
