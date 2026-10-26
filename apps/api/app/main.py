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
from .models import Project, Blueprint, Layout, Render, WallAnnotation, ModelWallCorrection, FusionCandidateReview
from .geometry import Geometry, fallback_geometry, validate_geometry
from .providers import extract_geometry, ProviderUnavailable, ProviderAuthenticationError, ProviderConfigurationError, ProviderOutputError
from .evidence import inspect_plan
from .reconcile import reconcile
from .geometry import Wall, Pt
from .pretrained_detector import DetectorResult, DetectorUnavailable, detect_objects
from .model_reconstruction import reconstruct, detection_audit
from .topology import audit_topology
from .missing_wall_evidence import gap_suggestions
from .exterior_recovery import suggest_bottom_runs
from .graph_reconstruction import propose_connected_geometry
from .wall_segmentation import infer_wall_mask, mask_centerlines, propose_mask_walls
from .yytsi_raster import predict_yytsi_raster
from .mask_topology import region_wall_lines
from .wall_run_normalization import consolidate_wall_runs
from .evidence_fusion import fuse_evidence

Path(settings.storage_path).mkdir(parents=True,exist_ok=True)
if settings.database_url.startswith('sqlite:///'):
    Path(settings.database_url.removeprefix('sqlite:///')).parent.mkdir(parents=True,exist_ok=True)
engine=create_engine(settings.database_url,connect_args={'check_same_thread':False} if settings.database_url.startswith('sqlite') else {})
SQLModel.metadata.create_all(engine)
app=FastAPI(title='Florp API',version='0.1.0')
app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origins.split(','),allow_credentials=True,allow_methods=['*'],allow_headers=['*'])

@app.get('/models/status')
def local_model_status():
    """Check local checkpoint configuration without loading models or exposing secrets."""
    from importlib.util import find_spec
    yolo_file=Path(settings.pretrained_yolo_weights).expanduser().resolve() if settings.pretrained_yolo_weights else None
    yytsi_dir=Path(settings.yytsi_run_dir).expanduser().resolve()
    return {
        'yolo':{
            'configured':bool(settings.pretrained_yolo_weights),
            'checkpoint_found':bool(yolo_file and yolo_file.is_file()),
            'dependency_installed':find_spec('ultralytics') is not None,
            'note':'Required by Auto-build 2D + 3D; separate from Yytsi segmentation.',
        },
        'segmentation':{
            'provider':settings.wall_segmentation_provider,
            'yytsi_weights_found':(yytsi_dir/settings.yytsi_checkpoint).is_file(),
            'yytsi_config_found':(yytsi_dir/'config.yaml').is_file(),
            'yytsi_dependency_installed':find_spec('buildingcv') is not None,
            'note':'Required by Experimental wall segmentation.',
        },
    }

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
@app.delete('/projects/{pid}')
def delete_project(pid:str):
    with Session(engine) as s:
        project=s.get(Project,pid)
        if not project:raise HTTPException(404,'Project not found')
        plans=list(s.exec(select(Blueprint).where(Blueprint.project_id==pid)).all())
        ids=[bp.id for bp in plans]
        for bid in ids:
            for table in (Render,ModelWallCorrection,WallAnnotation,FusionCandidateReview,Layout):
                for row in s.exec(select(table).where(table.blueprint_id==bid)).all():
                    s.delete(row)
        for bp in plans:s.delete(bp)
        s.delete(project)
        s.commit()
    root=Path(settings.storage_path).resolve()
    for bid in ids:
        folder=(root/bid).resolve()
        if folder.parent==root and folder.is_dir():shutil.rmtree(folder)
    return {'deleted':True,'blueprints_deleted':len(ids)}

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
@app.get('/blueprints/{bid}/topology')
def topology_report(bid: str):
    with Session(engine) as session:
        row=session.exec(select(Layout).where(Layout.blueprint_id==bid).order_by(Layout.version.desc())).first()
        if not row: raise HTTPException(404,'No layout')
        return audit_topology(Geometry.model_validate(row.geometry))

@app.post('/blueprints/{bid}/topology/propose')
def propose_topology(bid: str):
    # Saves a new unverified layout; original correction history stays available.
    with Session(engine) as session:
        bp=session.get(Blueprint,bid)
        if not bp:raise HTTPException(404,'Blueprint not found')
        last=session.exec(select(Layout).where(Layout.blueprint_id==bid).order_by(Layout.version.desc())).first()
        if not last:raise HTTPException(404,'No saved layout')
        if last.verified:raise HTTPException(409,'Verified layouts are immutable; create an unverified draft before proposing changes')
        try:
            proposal=propose_connected_geometry(Geometry.model_validate(last.geometry))
        except ValueError as exc:raise HTTPException(422,str(exc))
        row=Layout(blueprint_id=bid,version=last.version+1,verified=False,geometry=proposal.model_dump())
        session.add(row);session.commit();session.refresh(row)
        return {'layout':row,'topology':audit_topology(proposal)}

@app.get('/blueprints/{bid}/structural-graph')
def inspect_structural_graph(bid: str):
    from .structural_graph import build_structural_graph
    with Session(engine) as session:
        blueprint=session.get(Blueprint,bid)
        if blueprint is None:
            raise HTTPException(404,'Blueprint not found')
        layout=session.exec(select(Layout).where(Layout.blueprint_id==bid).order_by(Layout.version.desc())).first()
        if layout is None:
            raise HTTPException(404,'No layout')
        graph=build_structural_graph(Geometry.model_validate(layout.geometry))
        return {'layout_version':layout.version,'verified':False,'graph':graph.model_dump()}

@app.get('/blueprints/{bid}/missing-wall-suggestions')
def missing_wall_suggestions(bid:str):
    """Read-only proposals grounded in stored image and current saved geometry."""
    with Session(engine) as session:
        blueprint=session.get(Blueprint,bid)
        if not blueprint:raise HTTPException(404,'Blueprint not found')
        row=session.exec(select(Layout).where(Layout.blueprint_id==bid).order_by(Layout.version.desc())).first()
        if not row:raise HTTPException(404,'No layout')
        try:
            current=Geometry.model_validate(row.geometry)
            proposals=gap_suggestions(current,Path(blueprint.preview_path))
            perimeter=suggest_bottom_runs(current,Path(blueprint.preview_path))
        except ValueError as exc:raise HTTPException(422,str(exc))
        suggestions=[p.model_dump() for p in proposals]+[p.model_dump() for p in perimeter]
        return {'layout_version':row.version,'suggestions':suggestions,
                'warning':'Evidence-based proposals, not verified structural walls. Check source drawing before acceptance.'}

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

@app.post('/blueprints/{bid}/pretrained-reconstruct')
def pretrained_reconstruct(bid:str):
    with Session(engine) as session:
        bp=session.get(Blueprint,bid)
        if not bp:raise HTTPException(404,'Blueprint not found')
        previous=session.exec(select(Layout).where(Layout.blueprint_id==bid).order_by(Layout.version.desc())).first()
        if not previous:raise HTTPException(404,'No layout')
        try:
            detection=detect_objects(Path(bp.preview_path),bp.width,bp.height)
            geometry=reconstruct(detection,Geometry.model_validate(previous.geometry))
            geometry=propose_connected_geometry(geometry)
        except DetectorUnavailable as exc:raise HTTPException(424,str(exc))
        except ValueError as exc:raise HTTPException(422,str(exc))
        draft=Layout(blueprint_id=bid,version=previous.version+1,verified=False,geometry=geometry.model_dump())
        session.add(draft);session.commit();session.refresh(draft)
        return {'layout':draft,'detections':detection,'detection_audit':detection_audit(detection),'topology':audit_topology(geometry)}

class FusionReviewBody(BaseModel):
    preview_sha256: str
    candidate: dict
    decision: str
    input_manifest: dict = {}

@app.post('/blueprints/{bid}/fusion-reviews')
def review_fusion_candidate(bid:str, body:FusionReviewBody):
    import hashlib
    from .evidence_fusion import FusedCandidate
    if body.decision not in ('accept','reject','unsure','door','window'):
        raise HTTPException(422,'Decision must be accept, reject, unsure, door, or window')
    try:candidate=FusedCandidate.model_validate(body.candidate)
    except ValueError as exc:raise HTTPException(422,'Invalid fusion candidate') from exc
    with Session(engine) as session:
        bp=session.get(Blueprint,bid)
        if not bp:raise HTTPException(404,'Blueprint not found')
        preview_hash=hashlib.sha256(Path(bp.preview_path).read_bytes()).hexdigest()
        if body.preview_sha256!=preview_hash:
            raise HTTPException(409,'Blueprint preview changed; run comparison again')
        # The inference result must be anchored in the current review session.
        # This endpoint validates coordinates and provenance but does not rerun
        # expensive AI inference. Review events are untrusted until adjudicated.
        points=(candidate.start,candidate.end)
        if any(not (0<=p.x<=bp.width and 0<=p.y<=bp.height) for p in points):
            raise HTTPException(422,'Candidate outside blueprint')
        if candidate.start==candidate.end or not candidate.sources:
            raise HTTPException(422,'Candidate missing valid geometry or provenance')
        event=FusionCandidateReview(blueprint_id=bid,preview_sha256=preview_hash,
            candidate_id=candidate.id,category=candidate.category,
            decision=body.decision,candidate=candidate.model_dump(),
            input_manifest=body.input_manifest)
        session.add(event);session.commit();session.refresh(event)
        return {'review_id':event.id,'candidate_id':candidate.id,
                'decision':event.decision,'saved':True}

@app.get('/blueprints/{bid}/fusion-reviews')
def get_fusion_reviews(bid:str):
    with Session(engine) as session:
        if not session.get(Blueprint,bid):raise HTTPException(404,'Blueprint not found')
        events=list(session.exec(select(FusionCandidateReview).where(
            FusionCandidateReview.blueprint_id==bid).order_by(
                FusionCandidateReview.created_at)).all())
        return [{'preview_sha256':e.preview_sha256,'candidate_id':e.candidate_id,
                 'decision':e.decision,'candidate':e.candidate,
                 'input_manifest':e.input_manifest,'created_at':e.created_at.isoformat()} for e in events]

@app.post('/blueprints/{bid}/compare-extraction')
def compare_extraction(bid:str):
    """Read-only side-by-side model comparison; does not create a layout version.

    Both models consume the identical stored full-resolution PNG preview.
    A missing YOLO dependency yields an explicitly labeled mask-only result.
    """
    import base64, hashlib
    import numpy as np
    with Session(engine) as session:
        bp=session.get(Blueprint,bid)
        if not bp:raise HTTPException(404,'Blueprint not found')
        current=session.exec(select(Layout).where(Layout.blueprint_id==bid).order_by(Layout.version.desc())).first()
        if not current:raise HTTPException(404,'No layout')
        existing=Geometry.model_validate(current.geometry)
        preview_path=Path(bp.preview_path)
        try:
            provider=settings.wall_segmentation_provider.lower().strip()
            if provider=='yytsi':
                mask,metadata=predict_yytsi_raster(preview_path,bp.width,bp.height)
            elif provider=='ultralytics':
                mask,checkpoint=infer_wall_mask(preview_path,bp.width,bp.height)
                metadata={'provider':'Ultralytics/instance-segmentation','checkpoint':checkpoint}
            else:
                raise ValueError('Invalid segmentation provider')
            report=region_wall_lines(mask,min_length=max(22,min(bp.width,bp.height)//18))
            detection_error=None
            try:detector=detect_objects(preview_path,bp.width,bp.height)
            except DetectorUnavailable as err:
                detector=None
                detection_error=str(err)
            proposed,candidates,comparison=fuse_evidence(existing,mask,report,detector)
        except DetectorUnavailable as exc:raise HTTPException(424,str(exc))
        except ValueError as exc:raise HTTPException(422,str(exc))
        overlay=np.zeros((bp.height,bp.width,4),dtype=np.uint8)
        overlay[:,:,1]=160;overlay[:,:,2]=145
        overlay[:,:,3]=np.where(mask>0,130,0).astype(np.uint8)
        image=io.BytesIO()
        Image.fromarray(overlay,'RGBA').save(image,format='PNG')
        return {
            'input_manifest':{
                'source_preview_sha256':hashlib.sha256(preview_path.read_bytes()).hexdigest(),
                'width_px':bp.width,'height_px':bp.height,
                'segmentation_provider':metadata.get('provider'),
                'segmentation_checkpoint':metadata.get('checkpoint'),
                'segmentation_multiscale':metadata.get('multiscale'),
                'segmentation_wall_threshold':metadata.get('wall_threshold'),
                'yolo_provider':detector.provider if detector else None,
                'same_original_preview_for_both_models':True,
            },
            'base_layout_version':current.version,
            'proposal':proposed.model_dump(),
            'candidates':[c.model_dump() for c in candidates],
            'comparison':comparison.model_dump(),
            'detections':detector.model_dump() if detector else None,
            'yolo_error':detection_error,
            'segmentation':metadata,
            'mask_overlay_png_base64':base64.b64encode(image.getvalue()).decode('ascii'),
            'saved':False,
        }

@app.post('/blueprints/{bid}/segmentation/propose')
def segmentation_proposal(bid:str):
    """An explicit experiment: never overwrite a verified or manually edited layout."""
    with Session(engine) as session:
        bp=session.get(Blueprint,bid)
        if not bp:raise HTTPException(404,'Blueprint not found')
        previous=session.exec(select(Layout).where(Layout.blueprint_id==bid).order_by(Layout.version.desc())).first()
        if not previous:raise HTTPException(404,'No layout')
        current=Geometry.model_validate(previous.geometry)
        if previous.verified or current.structure_reviewed or any(w.id.startswith('user-') for w in current.walls):
            raise HTTPException(409,'Current layout contains approved or manually edited geometry. Save an independent experiment copy before applying segmentation.')
        try:
            provider=settings.wall_segmentation_provider.lower().strip()
            if provider=='yytsi':
                mask,metadata=predict_yytsi_raster(Path(bp.preview_path),bp.width,bp.height)
                checkpoint=metadata['checkpoint']
            elif provider=='ultralytics':
                mask,checkpoint=infer_wall_mask(Path(bp.preview_path),bp.width,bp.height)
                metadata={'provider':'Ultralytics/instance-segmentation','checkpoint':checkpoint}
            else:
                raise ValueError('WALL_SEGMENTATION_PROVIDER must be yytsi or ultralytics')
            report=region_wall_lines(mask,min_length=max(22,min(bp.width,bp.height)//18))
            raw_mask_line_count=report.line_count
            report=consolidate_wall_runs(report)
            if report.line_count==0:raise ValueError('Segmentation yielded no supported wall centerlines')
            draft=propose_mask_walls(current,report)
            draft=propose_connected_geometry(draft)
        except DetectorUnavailable as exc:raise HTTPException(424,str(exc))
        except ValueError as exc:raise HTTPException(422,str(exc))
        version=Layout(blueprint_id=bid,version=previous.version+1,verified=False,geometry=draft.model_dump())
        session.add(version);session.commit();session.refresh(version)
        # Return an inspectable pixel mask as an optional translucent PNG layer.
        # This is derived from actual model pixels, not from the simplified walls.
        import base64
        import numpy as np
        from PIL import Image as PillowImage
        rgba=np.zeros((bp.height,bp.width,4),dtype=np.uint8)
        rgba[:,:,1]=160
        rgba[:,:,2]=145
        rgba[:,:,3]=np.where(mask>0,135,0).astype(np.uint8)
        output=io.BytesIO()
        PillowImage.fromarray(rgba,'RGBA').save(output,format='PNG')
        return {'layout':version,'report':{'checkpoint':checkpoint,**metadata,'raw_mask_line_count':raw_mask_line_count,'normalized_mask_line_count':report.line_count,**report.model_dump()},
                'mask_overlay_png_base64':base64.b64encode(output.getvalue()).decode('ascii'),
                'topology':audit_topology(draft)}

@app.post('/blueprints/{bid}/extract')
async def extract(bid:str):
    with Session(engine) as s:bp=s.get(Blueprint,bid)
    if not bp:raise HTTPException(404,'Not found')
    data=Path(bp.preview_path).read_bytes()
    try:g=await extract_geometry(data,'image/png',bp.width,bp.height)
    except ProviderOutputError as e:raise HTTPException(424,str(e))
    except ProviderConfigurationError as e:raise HTTPException(424,str(e))
    except ProviderAuthenticationError as e:raise HTTPException(424,str(e))
    except ProviderUnavailable as e:raise HTTPException(424,str(e))
    except Exception as e:raise HTTPException(502,f'Vision provider error: {type(e).__name__}: {e}')
    evidence=inspect_plan(Path(bp.local_path),Path(bp.preview_path))
    if g.px_per_meter is None and evidence.automatic_scale:
        g.px_per_meter=evidence.automatic_scale.px_per_meter
        g.scale_source='provisional_auto'
        g.warnings.append('Scale inferred from '+str(evidence.automatic_scale.evidence_count)+' OCR/line clues; requires confirmation before verification')
    # Remote visual recognition is always a proposal; not user-confirmed.
    for wall in g.walls:wall.inferred=True
    for opening in g.openings:opening.inferred=True
    g.structure_reviewed=False
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
        model_reviews=list(s.exec(select(ModelWallCorrection).where(ModelWallCorrection.blueprint_id==bid)).all())
        fusion_reviews=list(s.exec(select(FusionCandidateReview).where(FusionCandidateReview.blueprint_id==bid)).all())
        walls=[w for w in Geometry.model_validate(layout.geometry).model_dump()['walls'] if w['id'].startswith('user-')] if layout else []
    return {'schema_version':2,'blueprint_id':bid,'image_width':bp.width,'image_height':bp.height,
      'annotations':[{'label':a.label,**a.coordinates} for a in annotations],
      'manually_drawn_walls':walls,
      'fusion_candidate_reviews':[{'candidate_id':r.candidate_id,'category':r.category,'decision':r.decision,'preview_sha256':r.preview_sha256,'candidate':r.candidate,'input_manifest':r.input_manifest,'created_at':r.created_at.isoformat()} for r in fusion_reviews],
      'model_wall_corrections':[{'model_wall_id':r.model_wall_id,'action':r.action,'original':r.original,'corrected':r.corrected,'layout_version':r.layout_version} for r in model_reviews],
      'note':'Review labels before training; this is not a trained detector.'}

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
    geometry: Geometry | None = None

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
        # Respect in-progress edits sent by the editor. Otherwise an opening
        # click could reload an older saved layout and discard drawn walls.
        g=(body.geometry or Geometry.model_validate(current.geometry)).model_copy(deep=True)
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
        same_wall=[o for o in g.openings if o.wall_id==body.wall_id]
        overlaps=lambda opening: (offset < opening.offset_m+opening.width_m
                                   and opening.offset_m < offset+width)
        matching=[o for o in same_wall if overlaps(o)]
        if matching:
            # Select the most relevant inferred proposal. Do not move it across
            # a different opening or mutate confirmed annotations.
            existing=min(matching,key=lambda o:abs(
                (o.offset_m+o.width_m/2)-(offset+width/2)))
            if not existing.inferred:
                raise HTTPException(409,'This opening is already confirmed; edit its dimensions in the review panel.')
            collides=any(o.id!=existing.id and
                offset < o.offset_m+o.width_m and o.offset_m < offset+width
                for o in same_wall)
            existing.kind=body.kind
            # Preserve its previous span rather than introducing a second
            # overlap when two predictions share one wall.
            if not collides:
                existing.offset_m=round(offset,3)
                existing.width_m=round(width,3)
            existing.height_m=2.1 if body.kind=='door' else 1.2
            existing.sill_m=0 if body.kind=='door' else .9
        else:
            opening=Opening(id='opening-'+uuid4().hex[:12],kind=body.kind,wall_id=body.wall_id,
              offset_m=round(offset,3),width_m=round(width,3),height_m=2.1 if body.kind=='door' else 1.2,
              sill_m=0 if body.kind=='door' else .9,inferred=True)
            g.openings.append(opening)
        g.structure_reviewed=False
        if not g.px_per_meter:
            g.warnings=list(dict.fromkeys(g.warnings+['Opening metrics are provisional; scale must be confirmed before verification']))
        row=Layout(blueprint_id=bid,version=current.version+1,verified=False,geometry=g.model_dump())
        s.add(row);s.commit();s.refresh(row)
        return row

class SaveLayout(BaseModel):
    geometry:Geometry
    verified:bool=False
    structure_reviewed:bool=False
@app.post('/blueprints/{bid}/layout')
def save_layout(bid:str,body:SaveLayout):
    with Session(engine) as session:
        if not session.get(Blueprint,bid):
            raise HTTPException(404,'Blueprint not found')
        last=session.exec(select(Layout).where(Layout.blueprint_id==bid).order_by(Layout.version.desc())).first()
        incoming=body.geometry.model_copy(deep=True)
        if body.structure_reviewed:
            incoming.structure_reviewed=True
        issues=validate_geometry(incoming)
        if body.verified and incoming.scale_source!='user_confirmed':
            issues.append('Confirm the scale using blueprint dimension evidence before metric verification')
        if body.verified and any(o.inferred for o in incoming.openings):
            issues.append('Confirm each provisional door/window dimension before metric verification')
        if body.verified and issues:
            raise HTTPException(422,{'message':'Metric verification blocked; wall review may still be saved separately','issues':issues})
        version=last.version+1 if last else 1
        row=Layout(blueprint_id=bid,version=version,verified=body.verified,geometry=incoming.model_dump())
        session.add(row)
        if body.structure_reviewed and last:
            old=Geometry.model_validate(last.geometry)
            before={w.id:w.model_dump() for w in old.walls if w.id.startswith('model-')}
            after={w.id:w.model_dump() for w in incoming.walls if w.id.startswith('model-')}
            for wall_id,original in before.items():
                corrected=after.get(wall_id)
                action='rejected' if corrected is None else (
                    'adjusted' if original['start']!=corrected['start'] or original['end']!=corrected['end'] else 'confirmed'
                )
                session.add(ModelWallCorrection(blueprint_id=bid,model_wall_id=wall_id,
                    action=action,original=original,corrected=corrected or {},layout_version=version))
        session.commit()
        session.refresh(row)
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
