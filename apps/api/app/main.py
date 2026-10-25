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
from .providers import extract_geometry, ProviderUnavailable, ProviderAuthenticationError, ProviderConfigurationError
from .evidence import inspect_plan
from .reconcile import reconcile
from .geometry import Wall, Pt
from .pretrained_detector import DetectorResult, DetectorUnavailable, detect_objects

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
    starting=fallback_geometry(bp.width,bp.height)
    evidence=inspect_plan(raw,preview)
    if evidence.automatic_scale:
        starting.px_per_meter=evidence.automatic_scale.px_per_meter
        starting.scale_source='provisional_auto'
        starting.warnings.append('Automatic metric scale is provisional: review a recognized dimension')
    layout=Layout(blueprint_id=bp.id,geometry=starting.model_dump())
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


@app.get('/vision/provider-check')
async def vision_provider_check():
    # No credentials are exposed. This endpoint only verifies model access.
    import httpx
    from .config import settings
    if not settings.llm_api_key:
        return {'configured':False,'message':'LLM_API_KEY not configured'}
    url=settings.llm_base_url.rstrip('/')+'/models'
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response=await client.get(url,headers={'Authorization':'Bearer '+settings.llm_api_key})
        if response.status_code in (401,403):
            return {'configured':True,'ok':False,'message':'Provider authentication rejected API key'}
        if response.status_code!=200:
            return {'configured':True,'ok':False,'message':'Provider model-list HTTP '+str(response.status_code)}
        ids={m.get('id') for m in response.json().get('data',[]) if isinstance(m,dict)}
        return {'configured':True,'ok':settings.llm_model in ids,'model':settings.llm_model,
          'message':'Model is listed by provider' if settings.llm_model in ids else 'Configured LLM_MODEL not found in provider model list; choose a vision-capable model'}
    except (httpx.HTTPError,ValueError,KeyError) as exc:
        return {'configured':True,'ok':False,'message':'Unable to validate provider models: '+type(exc).__name__}

@app.post('/blueprints/{bid}/pretrained-detections', response_model=DetectorResult)
def pretrained_detections(bid: str):
    with Session(engine) as s:
        bp=s.get(Blueprint,bid)
        if not bp:raise HTTPException(404,'Blueprint not found')
    try:
        return detect_objects(Path(bp.preview_path),bp.width,bp.height)
    except DetectorUnavailable as exc:
        raise HTTPException(424,str(exc))

@app.post('/blueprints/{bid}/extract')
async def extract(bid:str):
    with Session(engine) as s:bp=s.get(Blueprint,bid)
    if not bp:raise HTTPException(404,'Not found')
    data=Path(bp.preview_path).read_bytes()
    try:g=await extract_geometry(data,'image/png',bp.width,bp.height)
    except ProviderConfigurationError as e:raise HTTPException(424,str(e))
    except ProviderAuthenticationError as e:raise HTTPException(424,str(e))
    except ProviderUnavailable as e:raise HTTPException(424,str(e))
    except Exception as e:raise HTTPException(502,f'Vision provider error: {type(e).__name__}: {e}')
    evidence=inspect_plan(Path(bp.local_path),Path(bp.preview_path))
    if g.px_per_meter is None and evidence.automatic_scale:
        g.px_per_meter=evidence.automatic_scale.px_per_meter
        g.scale_source='provisional_auto'
        g.warnings.append('Scale inferred from '+str(evidence.automatic_scale.evidence_count)+' OCR/line clues; requires confirmation before verification')
    g=reconcile(g,evidence)
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

class ProvisionalOpeningInput(BaseModel):
    kind: str
    wall_id: str
    fraction: float

@app.post('/blueprints/{bid}/openings/propose')
def propose_opening(bid:str,body:ProvisionalOpeningInput):
    # Persist a draft without requiring user to manually calibrate measurement.
    # When scale is absent, use an explicit provisional estimate; never mark verified.
    from uuid import uuid4
    from math import hypot
    from .geometry import Opening
    if body.kind not in ('door','window') or not 0<=body.fraction<=1:
        raise HTTPException(422,'Invalid opening type or position')
    with Session(engine) as s:
        bp=s.get(Blueprint,bid)
        if not bp:raise HTTPException(404,'Blueprint not found')
        current=s.exec(select(Layout).where(Layout.blueprint_id==bid).order_by(Layout.version.desc())).first()
        if not current:raise HTTPException(404,'Layout not found')
        g=Geometry.model_validate(current.geometry).model_copy(deep=True)
        edges={w.id:(w.start,w.end) for w in g.walls}
        for room in g.rooms:
            for i,p in enumerate(room.points):
                edges['boundary:'+room.id+':'+str(i)]=(p,room.points[(i+1)%len(room.points)])
        if body.wall_id not in edges:raise HTTPException(422,'Wall no longer exists')
        a,b=edges[body.wall_id]
        length_px=hypot(b.x-a.x,b.y-a.y)
        if length_px<10:raise HTTPException(422,'Wall too short')
        # This value is only a draft metric convenience if no dimension is verified.
        ppm=g.px_per_meter or 60.0
        length_m=length_px/ppm
        width=min(.9 if body.kind=='door' else 1.2,length_m*.6)
        if width<.12:raise HTTPException(422,'Wall too short')
        offset=max(0,min(length_m-width,body.fraction*length_m-width/2))
        # Fail safely if the tentative span collides with an existing opening.
        for existing in g.openings:
            if existing.wall_id==body.wall_id and offset < existing.offset_m+existing.width_m and existing.offset_m < offset+width:
                raise HTTPException(409,'Opening overlaps an existing opening')
        opening=Opening(id='opening-'+uuid4().hex[:12],kind=body.kind,wall_id=body.wall_id,
          offset_m=round(offset,3),width_m=round(width,3),height_m=2.1 if body.kind=='door' else 1.2,
          sill_m=0 if body.kind=='door' else .9,inferred=True)
        g.openings.append(opening)
        if not g.px_per_meter:
            g.warnings=list(dict.fromkeys(g.warnings+['Opening metrics are provisional; scale must be confirmed before verification']))
        row=Layout(blueprint_id=bid,version=current.version+1,verified=False,geometry=g.model_dump())
        s.add(row);s.commit();s.refresh(row)
        return row

class SaveLayout(BaseModel):
    geometry:Geometry
    verified:bool=False
@app.post('/blueprints/{bid}/layout')
def save_layout(bid:str,body:SaveLayout):
    with Session(engine) as s:
        if not s.get(Blueprint,bid):
            raise HTTPException(404,'Not found')
        last=s.exec(select(Layout).where(Layout.blueprint_id==bid).order_by(Layout.version.desc())).first()
        warnings=validate_geometry(body.geometry)
        if body.verified and body.geometry.scale_source=='provisional_auto':
            warnings.append('Review and confirm the inferred physical scale first')
    if body.verified and body.geometry.openings and any('provisional' in w.lower() for w in body.geometry.warnings):
            warnings.append('Confirm scale and provisional opening dimensions before verification')
    if body.verified and warnings:
        raise HTTPException(422,{'message':'Resolve validation issues before verification','issues':warnings})
    row=Layout(blueprint_id=bid,version=(last.version+1 if last else 1),verified=body.verified,geometry=body.geometry.model_dump())
    s.add(row);s.commit();s.refresh(row)
    return row
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
