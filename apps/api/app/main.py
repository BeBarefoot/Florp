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
from .models import Project, Blueprint, Layout, Render
from .geometry import Geometry, fallback_geometry, validate_geometry
from .providers import extract_geometry, ProviderUnavailable

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
@app.post('/blueprints/{bid}/extract')
async def extract(bid:str):
    with Session(engine) as s:bp=s.get(Blueprint,bid)
    if not bp:raise HTTPException(404,'Not found')
    data=Path(bp.preview_path).read_bytes()
    try:g=await extract_geometry(data,'image/png',bp.width,bp.height)
    except ProviderUnavailable as e:raise HTTPException(424,str(e))
    except Exception as e:raise HTTPException(502,f'Vision provider error: {type(e).__name__}: {e}')
    warnings=validate_geometry(g);g.warnings.extend(warnings)
    with Session(engine) as s:
        last=s.exec(select(Layout).where(Layout.blueprint_id==bid).order_by(Layout.version.desc())).first()
        row=Layout(blueprint_id=bid,version=(last.version+1 if last else 1),geometry=g.model_dump())
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
