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
from .models import Project, Blueprint, Layout, Render, WallAnnotation, ModelWallCorrection, FusionCandidateReview, ExtractionEvaluation, PlanGraphRevision
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
            for table in (Render,ModelWallCorrection,WallAnnotation,FusionCandidateReview,ExtractionEvaluation,PlanGraphRevision,Layout):
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
class EvaluationStartBody(BaseModel):
    provider: str
    image_sha256: str
    base_layout_version: int
    geometry: Geometry

class EvaluationFinishBody(BaseModel):
    geometry: Geometry
    correction_seconds: int
    notes: str = ''
    human_reviewed: bool = False

@app.post('/blueprints/{bid}/evaluations')
def start_extraction_evaluation(bid:str,body:EvaluationStartBody):
    """Store an immutable AI baseline BEFORE manual corrections."""
    import hashlib
    from .extraction_exports import normalize_florp_geometry
    if body.provider not in ('florp-fusion','florp-yolo','florp-yytsi'):
        raise HTTPException(422,'Unsupported baseline provider')
    with Session(engine) as session:
        bp=session.get(Blueprint,bid)
        if not bp:raise HTTPException(404,'Blueprint not found')
        current=session.exec(select(Layout).where(Layout.blueprint_id==bid).order_by(Layout.version.desc())).first()
        if not current:raise HTTPException(404,'No saved layout')
        preview=Path(bp.preview_path)
        digest=hashlib.sha256(preview.read_bytes()).hexdigest()
        if digest!=body.image_sha256 or current.version!=body.base_layout_version:
            raise HTTPException(409,'Image or saved layout changed; run extraction again')
        if body.geometry.width_px!=bp.width or body.geometry.height_px!=bp.height:
            raise HTTPException(422,'Baseline dimensions do not match blueprint')
        if not body.geometry.walls:raise HTTPException(422,'No detected walls to evaluate')
        baseline=normalize_florp_geometry(preview,body.geometry.model_dump(),body.provider)
        row=ExtractionEvaluation(blueprint_id=bid,image_sha256=digest,
            provider=body.provider,base_layout_version=current.version,
            baseline=baseline.model_dump(mode='json'))
        session.add(row);session.commit();session.refresh(row)
        return {'id':row.id,'status':row.status,'provider':row.provider,
                'baseline_walls':len(baseline.walls),'created_at':row.created_at}

@app.get('/blueprints/{bid}/reviewed-geometry-export')
def reviewed_geometry_export(bid:str):
    """Portable draft + current review labels. Never claims independent ground truth."""
    import hashlib
    with Session(engine) as session:
        bp=session.get(Blueprint,bid)
        if bp is None:raise HTTPException(404,'Blueprint not found')
        layout=session.exec(select(Layout).where(Layout.blueprint_id==bid)
                            .order_by(Layout.version.desc())).first()
        if layout is None:raise HTTPException(404,'No saved layout')
        digest=hashlib.sha256(Path(bp.preview_path).read_bytes()).hexdigest()
        rows=session.exec(select(FusionCandidateReview).where(
            FusionCandidateReview.blueprint_id==bid,
            FusionCandidateReview.preview_sha256==digest).order_by(
            FusionCandidateReview.created_at,FusionCandidateReview.id)).all()
        latest={}
        for row in rows:latest[row.candidate_id]=row
        labels=[{'candidate_id':row.candidate_id,'decision':row.decision,
                 'candidate':row.candidate,'input_manifest':row.input_manifest}
                for row in latest.values()]
        return {'schema_version':1,'source_preview_sha256':digest,
                'width_px':bp.width,'height_px':bp.height,
                'layout_version':layout.version,'layout_verified':layout.verified,
                'structure_reviewed':bool(layout.geometry.get('structure_reviewed',False)),
                'geometry':layout.geometry,'review_labels':labels,
                'source':'saved geometry + latest append-only human review decisions',
                'ground_truth_status':'not independently validated',
                'warning':'Approved candidate labels and a saved draft are not automatically complete training ground truth.'}

@app.get('/blueprints/{bid}/evaluations')
def list_extraction_evaluations(bid:str):
    with Session(engine) as session:
        if not session.get(Blueprint,bid):raise HTTPException(404,'Blueprint not found')
        rows=session.exec(select(ExtractionEvaluation).where(
            ExtractionEvaluation.blueprint_id==bid).order_by(
            ExtractionEvaluation.created_at.desc())).all()
        return [{'id':r.id,'provider':r.provider,'status':r.status,
                 'base_layout_version':r.base_layout_version,
                 'image_sha256':r.image_sha256,
                 'metrics':r.metrics if r.status=='completed' else None,
                 'correction_seconds':r.correction_seconds,
                 'notes':r.notes,'created_at':r.created_at} for r in rows]

@app.get('/blueprints/{bid}/evaluations/{evaluation_id}')
def get_extraction_evaluation(bid:str,evaluation_id:str):
    """Portable export with baseline and human reference in original image pixels."""
    with Session(engine) as session:
        row=session.get(ExtractionEvaluation,evaluation_id)
        if not row or row.blueprint_id!=bid:
            raise HTTPException(404,'Evaluation not found')
        return {'schema_version':1,'id':row.id,'blueprint_id':row.blueprint_id,
                'image_sha256':row.image_sha256,'provider':row.provider,
                'base_layout_version':row.base_layout_version,
                'status':row.status,'baseline':row.baseline,
                'reference':row.reference if row.status=='completed' else None,
                'metrics':row.metrics if row.status=='completed' else None,
                'correction_seconds':row.correction_seconds,
                'notes':row.notes,'created_at':row.created_at,
                'completed_at':row.completed_at}

@app.post('/blueprints/{bid}/evaluations/{evaluation_id}/finish')
def finish_extraction_evaluation(bid:str,evaluation_id:str,body:EvaluationFinishBody):
    """Commit attested human reference; comparisons never overwrite layouts."""
    import hashlib
    from datetime import datetime,timezone
    from .extraction_benchmark import PlanPrediction,compare
    from .extraction_exports import normalize_florp_geometry
    if not body.human_reviewed:
        raise HTTPException(422,'Explicit independent human review required')
    if not 0<=body.correction_seconds<=86400:
        raise HTTPException(422,'Correction duration must be between 0 and 24 hours')
    if len(body.notes)>2000:raise HTTPException(422,'Notes are too long')
    with Session(engine) as session:
        row=session.get(ExtractionEvaluation,evaluation_id)
        if row is None or row.blueprint_id!=bid:raise HTTPException(404,'Evaluation not found')
        if row.status!='baseline':raise HTTPException(409,'Evaluation already completed')
        bp=session.get(Blueprint,bid)
        if bp is None:raise HTTPException(404,'Blueprint not found')
        preview=Path(bp.preview_path)
        if hashlib.sha256(preview.read_bytes()).hexdigest()!=row.image_sha256:
            raise HTTPException(409,'Source image changed')
        if (body.geometry.width_px,body.geometry.height_px)!=(bp.width,bp.height):
            raise HTTPException(422,'Reference image dimensions mismatch')
        if not body.geometry.walls:
            raise HTTPException(422,'Reference must contain independently checked walls')
        # Starter IDs are not reliable proof of an untouched placeholder:
        # legitimate user edits can retain those IDs alongside new walls.
        # Reject only an entirely unmodified fallback wall set. A reviewer
        # must still remove any remaining fictitious placeholders manually.
        starter=fallback_geometry(bp.width,bp.height)
        def segment_key(w):
            return tuple(sorted(((round(w.start.x,3),round(w.start.y,3)),
                                 (round(w.end.x,3),round(w.end.y,3)))))
        observed={segment_key(w) for w in body.geometry.walls}
        placeholders={segment_key(w) for w in starter.walls}
        if observed==placeholders and len(body.geometry.walls)==len(starter.walls):
            raise HTTPException(422,'Unmodified starter outline is not reviewed ground truth; correct or replace its walls first')
        reference=normalize_florp_geometry(preview,body.geometry.model_dump(),'human-reviewed')
        baseline=PlanPrediction.model_validate(row.baseline)
        metrics=compare(reference,baseline)
        row.reference=reference.model_dump(mode='json')
        row.metrics=metrics
        row.correction_seconds=body.correction_seconds
        row.notes=body.notes.strip()
        row.status='completed'
        row.completed_at=datetime.now(timezone.utc)
        session.add(row);session.commit()
        return {'id':row.id,'status':row.status,'metrics':metrics,
                'correction_seconds':row.correction_seconds}

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

class OpeningAssociationPreviewBody(BaseModel):
    geometry: Geometry

@app.post('/blueprints/{bid}/openings/association-preview')
def preview_reviewed_openings(bid:str,body:OpeningAssociationPreviewBody):
    """Visual-only door/window host suggestions, no fabricated metric cutouts.

    Reads latest classification per candidate from the saved review audit.
    Physical openings require user-confirmed scale and geometry verification.
    """
    import hashlib
    from .opening_review import OpeningHint, associate_opening
    from .connectivity_preview import without_starter
    with Session(engine) as session:
        blueprint=session.get(Blueprint,bid)
        if blueprint is None:raise HTTPException(404,'Blueprint not found')
        if (body.geometry.width_px,body.geometry.height_px)!=(blueprint.width,blueprint.height):
            raise HTTPException(422,'Geometry source dimensions mismatch')
        digest=hashlib.sha256(Path(blueprint.preview_path).read_bytes()).hexdigest()
        rows=session.exec(select(FusionCandidateReview).where(
            FusionCandidateReview.blueprint_id==bid,
            FusionCandidateReview.preview_sha256==digest).order_by(
            FusionCandidateReview.created_at,FusionCandidateReview.id)).all()
        latest={}
        for row in rows:latest[row.candidate_id]=row
        geometry=without_starter(body.geometry)
        items=[]
        for key,review in latest.items():
            if review.decision not in ('door','window'):continue
            candidate=review.candidate
            a,b=candidate.get('start'),candidate.get('end')
            if not isinstance(a,dict) or not isinstance(b,dict):continue
            try:
                x1,x2=sorted((float(a['x']),float(b['x'])))
                y1,y2=sorted((float(a['y']),float(b['y'])))
                if not all(0<=x<=blueprint.width for x in (x1,x2)) or not all(
                    0<=y<=blueprint.height for y in (y1,y2)):continue
                hint=OpeningHint(candidate_id=key,kind=review.decision,
                    x1=x1,y1=y1,x2=x2,y2=y2,source_confidence=0.,
                    reason='Human-classified visual opening evidence')
                attached=associate_opening(geometry,hint,max_distance_px=12.)
            except (ValueError,TypeError,KeyError):continue
            items.append({'candidate_id':key,'kind':review.decision,
                          'start':a,'end':b,'host_wall_id':attached.wall_id,
                          'fraction':attached.fraction,
                          'status':'proposed' if attached.wall_id else 'unresolved',
                          'reason':attached.reason})
        items.sort(key=lambda item:(item['status']!='proposed',item['candidate_id']))
        return {'saved':False,'confirmed_metric_openings':len(body.geometry.openings),
                'scale_confirmed':body.geometry.scale_source=='user_confirmed',
                'proposed':sum(item['status']=='proposed' for item in items),
                'unresolved':sum(item['status']=='unresolved' for item in items),
                'items':items,
                'warning':'Review each host wall and calibrate scale before creating 3D openings. No metric cutout was generated.'}

class ConnectivityPreviewBody(BaseModel):
    geometry: Geometry
    tolerance_px: float = 5.0

@app.post('/blueprints/{bid}/connectivity/preview')
def preview_wall_connectivity(bid:str,body:ConnectivityPreviewBody):
    """Pure geometry proposal; no changes to a layout, review or training data."""
    from .connectivity_preview import preview_connectivity
    with Session(engine) as session:
        blueprint=session.get(Blueprint,bid)
        if blueprint is None:raise HTTPException(404,'Blueprint not found')
        if (body.geometry.width_px,body.geometry.height_px)!=(blueprint.width,blueprint.height):
            raise HTTPException(422,'Draft dimensions mismatch the source image')
        if not body.geometry.walls:raise HTTPException(422,'No stored walls to connect')
        try:proposal=preview_connectivity(body.geometry,body.tolerance_px)
        except ValueError as exc:raise HTTPException(422,str(exc)) from exc
        return {'saved':False,**proposal.model_dump()}


class CreateCanonicalPlanBody(BaseModel):
    expected_layout_version: int

@app.post('/blueprints/{bid}/canonical-plan/preview')
def preview_canonical_plan(bid: str):
    """Read-only conversion; never writes canonical or legacy data."""
    from .graph_adapter import from_geometry
    from .graph_validation import validate_plan
    with Session(engine) as session:
        if not session.get(Blueprint,bid):raise HTTPException(404,'Blueprint not found')
        layout=session.exec(select(Layout).where(Layout.blueprint_id==bid).order_by(Layout.version.desc())).first()
        if layout is None:raise HTTPException(404,'No layout')
        plan=from_geometry(Geometry.model_validate(layout.geometry))
        return {'saved':False,'source_layout_version':layout.version,
                'graph':plan.model_dump(mode='json'),'validation_issues':validate_plan(plan)}

@app.post('/blueprints/{bid}/canonical-plan/revisions')
def create_canonical_revision(bid: str, body: CreateCanonicalPlanBody):
    """Explicit opt-in snapshot derived server-side from current saved layout."""
    from .graph_adapter import from_geometry
    from .graph_validation import require_valid
    from sqlalchemy.exc import IntegrityError
    with Session(engine) as session:
        if not session.get(Blueprint,bid):raise HTTPException(404,'Blueprint not found')
        layout=session.exec(select(Layout).where(Layout.blueprint_id==bid).order_by(Layout.version.desc())).first()
        if not layout:raise HTTPException(404,'No layout')
        if layout.version!=body.expected_layout_version:
            raise HTTPException(409,'Saved layout changed; refresh canonical plan preview')
        latest=session.exec(select(PlanGraphRevision).where(
            PlanGraphRevision.blueprint_id==bid).order_by(PlanGraphRevision.version.desc())).first()
        if latest and latest.source_layout_id==layout.id:
            raise HTTPException(409,'Canonical revision for this layout already exists; use operations')
        plan=from_geometry(Geometry.model_validate(layout.geometry))
        try:require_valid(plan)
        except ValueError as exc:raise HTTPException(422,str(exc)) from exc
        revision=PlanGraphRevision(blueprint_id=bid,source_layout_id=layout.id,
            source_layout_version=layout.version,version=latest.version+1 if latest else 1,
            parent_revision_id=latest.id if latest else None,
            operation={'kind':'import_legacy'},graph=plan.model_dump(mode='json'))
        session.add(revision)
        try:session.commit()
        except IntegrityError as exc:
            session.rollback();raise HTTPException(409,'Concurrent revision update; refresh') from exc
        session.refresh(revision)
        return revision

@app.get('/blueprints/{bid}/canonical-plan/revisions/latest')
def latest_canonical_revision(bid: str):
    with Session(engine) as session:
        if not session.get(Blueprint,bid):raise HTTPException(404,'Blueprint not found')
        revision=session.exec(select(PlanGraphRevision).where(
            PlanGraphRevision.blueprint_id==bid).order_by(PlanGraphRevision.version.desc())).first()
        if not revision:raise HTTPException(404,'No canonical plan revision yet')
        layout=session.exec(select(Layout).where(Layout.blueprint_id==bid).order_by(Layout.version.desc())).first()
        return {'revision':revision,'stale':not layout or layout.id!=revision.source_layout_id}

@app.post('/blueprints/{bid}/canonical-plan/revisions/{revision_id}/operations')
def edit_canonical_revision(bid: str,revision_id: str,operation: dict):
    """Atomic append-only graph edit. Legacy layout/3D is never overwritten."""
    from .plan_graph import CanonicalPlan
    from .graph_operations import GraphOperation, apply_operation
    from pydantic import ValidationError
    from sqlalchemy.exc import IntegrityError
    with Session(engine) as session:
        if not session.get(Blueprint,bid):raise HTTPException(404,'Blueprint not found')
        latest=session.exec(select(PlanGraphRevision).where(
            PlanGraphRevision.blueprint_id==bid).order_by(PlanGraphRevision.version.desc())).first()
        if latest is None or latest.id!=revision_id:
            raise HTTPException(409,'Stale revision; reload the latest canonical graph')
        layout=session.exec(select(Layout).where(Layout.blueprint_id==bid).order_by(Layout.version.desc())).first()
        if layout is None or layout.id!=latest.source_layout_id:
            raise HTTPException(409,'Legacy layout changed; re-import the canonical plan')
        try:
            command=GraphOperation.model_validate(operation)
            next_plan=apply_operation(CanonicalPlan.model_validate(latest.graph),command)
        except (ValueError,ValidationError) as exc:
            raise HTTPException(422,str(exc)) from exc
        row=PlanGraphRevision(blueprint_id=bid,source_layout_id=latest.source_layout_id,
            source_layout_version=latest.source_layout_version,version=latest.version+1,
            parent_revision_id=latest.id,operation=command.model_dump(mode='json',exclude_none=True),
            graph=next_plan.model_dump(mode='json'))
        session.add(row)
        try:session.commit()
        except IntegrityError as exc:
            session.rollback();raise HTTPException(409,'Concurrent revision update; refresh') from exc
        session.refresh(row)
        return row

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

class MergeFusionDraftBody(BaseModel):
    """Apply previously recorded wall approvals to the latest saved geometry."""
    preview_sha256: str
    layout_version: int
    candidate_ids: list[str]
    geometry: Geometry

@app.post('/blueprints/{bid}/fusion-draft/merge')
def merge_reviewed_fusion_walls(bid:str,body:MergeFusionDraftBody):
    """Read-only merge; never replace corrected walls, openings or stored layouts.

    The comparison's old layout version is intentionally irrelevant. We only
    require that the source image and CURRENT saved geometry have not changed.
    Approvals must exist in the append-only fusion review history.
    """
    import hashlib
    from .evidence_fusion import FusedCandidate
    from .geometry import Wall
    if len(body.candidate_ids)>500 or len(body.candidate_ids)!=len(set(body.candidate_ids)):
        raise HTTPException(422,'Invalid or duplicate requested wall IDs')
    with Session(engine) as session:
        bp=session.get(Blueprint,bid)
        if bp is None:raise HTTPException(404,'Blueprint not found')
        preview=Path(bp.preview_path)
        actual_hash=hashlib.sha256(preview.read_bytes()).hexdigest()
        if body.preview_sha256!=actual_hash:
            raise HTTPException(409,'Blueprint image changed; re-extract before applying reviews')
        current=session.exec(select(Layout).where(Layout.blueprint_id==bid)
                             .order_by(Layout.version.desc())).first()
        if current is None:raise HTTPException(404,'No saved layout')
        if body.layout_version!=current.version or body.geometry.model_dump()!=Geometry.model_validate(current.geometry).model_dump():
            raise HTTPException(409,'Current saved geometry changed; reload before merging approvals')
        reviews=list(session.exec(select(FusionCandidateReview).where(
            FusionCandidateReview.blueprint_id==bid,
            FusionCandidateReview.preview_sha256==actual_hash
        ).order_by(FusionCandidateReview.created_at, FusionCandidateReview.id)).all())
        latest={}
        for review in reviews:latest[review.candidate_id]=review
        updated=body.geometry.model_copy(deep=True)
        old_ids={wall.id for wall in updated.walls}
        added=0;already=0;ignored=0
        for candidate_id in body.candidate_ids:
            review=latest.get(candidate_id)
            if review is None or review.decision!='accept':
                ignored+=1
                continue
            if candidate_id in old_ids:
                already+=1
                continue
            try:candidate=FusedCandidate.model_validate(review.candidate)
            except ValueError:
                ignored+=1
                continue
            if candidate.id!=candidate_id or any(
                not(0<=p.x<=bp.width and 0<=p.y<=bp.height)
                for p in (candidate.start,candidate.end)
            ):
                ignored+=1
                continue
            if candidate.start==candidate.end:
                ignored+=1
                continue
            updated.walls.append(Wall(id=candidate.id,start=candidate.start,
                                      end=candidate.end,inferred=True))
            old_ids.add(candidate.id)
            added+=1
        if added:
            updated.structure_reviewed=False
            updated.warnings=list(dict.fromkeys(updated.warnings+[
                'Reviewed wall labels merged into unsaved geometry; check positions before saving.'
            ]))
        return {'saved':False,'geometry':updated.model_dump(),
                'added':added,'already_present':already,'ignored':ignored,
                'layout_version':current.version}

class OpeningReviewDraftBody(BaseModel):
    geometry: Geometry
    hint: dict

@app.post('/blueprints/{bid}/opening-review/draft')
def draft_reviewed_opening(bid:str,body:OpeningReviewDraftBody):
    """Return modified UNSAVED draft; never writes a layout or moves confirmed openings."""
    from .opening_review import OpeningHint,associate_opening,create_opening
    with Session(engine) as session:
        if not session.get(Blueprint,bid):raise HTTPException(404,'Blueprint not found')
    hint=OpeningHint.model_validate(body.hint)
    # Comparison-time hosts may no longer exist or may have moved. Recompute
    # against the actual draft, never trust a stale model-proposal host ID.
    hint=associate_opening(body.geometry,hint.model_copy(update={'wall_id':None,'fraction':None}))
    updated,status=create_opening(body.geometry,hint)
    return {'geometry':updated.model_dump(),'status':status,'hint':hint.model_dump()}

@app.get('/extraction/raster2seq/status')
def raster2seq_status():
    from .raster2seq_adapter import Raster2SeqUnavailable
    root=Path(settings.raster2seq_root).expanduser()
    python_bin=Path(settings.raster2seq_python).expanduser()
    ready=bool(settings.raster2seq_enabled and root.is_dir()
               and (root/'predict.py').is_file() and python_bin.is_file())
    return {'enabled':settings.raster2seq_enabled,'configured':ready,
            'device':settings.raster2seq_device,
            'checkpoint':settings.raster2seq_checkpoint,
            'license':'Checkpoint CC BY-NC 4.0; evaluation only unless separately licensed',
            'reason':None if ready else
              'Set RASTER2SEQ_ENABLED=true, RASTER2SEQ_ROOT and RASTER2SEQ_PYTHON to isolated Linux/CUDA environment'}

@app.post('/blueprints/{bid}/compare-raster2seq')
def compare_raster2seq(bid:str):
    """Run independent room-polygon model; never write project or geometry."""
    import hashlib
    from .raster2seq_adapter import Raster2SeqUnavailable,run_raster2seq
    if not settings.raster2seq_enabled:
        raise HTTPException(424,'Raster2Seq disabled; configure isolated noncommercial evaluation runtime')
    with Session(engine) as session:
        bp=session.get(Blueprint,bid)
        if bp is None:raise HTTPException(404,'Blueprint not found')
        current=session.exec(select(Layout).where(Layout.blueprint_id==bid)
                             .order_by(Layout.version.desc())).first()
        if current is None:raise HTTPException(404,'No saved layout')
        preview=Path(bp.preview_path)
        if not preview.is_file():raise HTTPException(404,'Blueprint preview missing')
        digest=hashlib.sha256(preview.read_bytes()).hexdigest()
        try:
            rooms,metadata=run_raster2seq(preview,
                root=Path(settings.raster2seq_root),
                python_exec=Path(settings.raster2seq_python),
                device=settings.raster2seq_device,
                checkpoint=settings.raster2seq_checkpoint,
                timeout_seconds=settings.raster2seq_timeout_seconds)
        except Raster2SeqUnavailable as exc:raise HTTPException(424,str(exc)) from exc
        except ValueError as exc:raise HTTPException(422,str(exc)) from exc
        interior=[room.model_dump() for room in rooms if room.category_id not in (9,10)]
        symbols=[{'kind':'window' if room.category_id==9 else 'door',
                  'points':room.points} for room in rooms if room.category_id in (9,10)]
        return {'saved':False,'image_sha256':digest,'base_layout_version':current.version,
                'width_px':bp.width,'height_px':bp.height,
                'rooms':interior,'opening_symbols':symbols,
                'metadata':metadata,
                'note':'Unverified room and opening-symbol polygons; no calibrated scale, wall thickness or 3D cutouts'}

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
            from .geometry_review_agent import review_geometry
            agent_suggestions=review_geometry(proposed,candidates,mask)
            opening_hints=[]
            if detector is not None:
                from .opening_review import OpeningHint,associate_opening
                for i,box in enumerate(detector.boxes):
                    if box.category not in ('door','window'):continue
                    hint=OpeningHint(candidate_id=f'opening-box-{i}',kind=box.category,
                        x1=box.x1,y1=box.y1,x2=box.x2,y2=box.y2,
                        source_confidence=box.confidence,reason='YOLO detection; unverified')
                    opening_hints.append(associate_opening(proposed,hint).model_dump())
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
                'inference_padding':{'enabled':settings.inference_border_enabled,
                                     'fraction':settings.inference_border_fraction,
                                     'min_px':settings.inference_border_min_px},
                'same_original_preview_for_both_models':True,
            },
            'base_layout_version':current.version,
            'proposal':proposed.model_dump(),
            'candidates':[c.model_dump() for c in candidates],
            'opening_hints':opening_hints,
            'geometry_review':{'suggestions':[p.model_dump() for p in agent_suggestions],
                'explanation':'Heuristic source-backed review priorities; no wall is approved automatically',
                'auto_applied':False},
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

class RestoreCanonicalBody(BaseModel):
    target_revision_id: str


def _current_graph(session: Session, bid: str, revision_id: str):
    """Common optimistic concurrency guard for canonical mutations."""
    if not session.get(Blueprint,bid):
        raise HTTPException(404,'Blueprint not found')
    latest=session.exec(select(PlanGraphRevision).where(
        PlanGraphRevision.blueprint_id==bid).order_by(PlanGraphRevision.version.desc())).first()
    if latest is None or latest.id!=revision_id:
        raise HTTPException(409,'Stale revision; reload the latest canonical graph')
    layout=session.exec(select(Layout).where(Layout.blueprint_id==bid).order_by(Layout.version.desc())).first()
    if layout is None or layout.id!=latest.source_layout_id:
        raise HTTPException(409,'Legacy layout changed; re-import the canonical plan')
    return latest


def _append_graph(session: Session, latest: PlanGraphRevision, graph: dict, operation: dict):
    from sqlalchemy.exc import IntegrityError
    row=PlanGraphRevision(blueprint_id=latest.blueprint_id,
        source_layout_id=latest.source_layout_id,source_layout_version=latest.source_layout_version,
        version=latest.version+1,parent_revision_id=latest.id,operation=operation,graph=graph)
    session.add(row)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409,'Concurrent revision update; refresh') from exc
    session.refresh(row)
    return row


@app.get('/blueprints/{bid}/canonical-plan/revisions/{revision_id}/geometry')
def canonical_geometry(bid: str, revision_id: str):
    """Read-only projection of one immutable revision for both 2D and 3D."""
    from .plan_graph import CanonicalPlan
    from .graph_adapter import to_geometry
    with Session(engine) as session:
        revision=session.get(PlanGraphRevision,revision_id)
        if revision is None or revision.blueprint_id!=bid:
            raise HTTPException(404,'Revision not found')
        try:
            geometry=to_geometry(CanonicalPlan.model_validate(revision.graph))
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
        return {'revision_id':revision.id,'geometry':geometry.model_dump(mode='json')}


@app.post('/blueprints/{bid}/canonical-plan/revisions/{revision_id}/restore')
def restore_canonical_revision(bid: str, revision_id: str, body: RestoreCanonicalBody):
    """Undo/restore by appending a snapshot, never deleting revision history."""
    from .plan_graph import CanonicalPlan
    from .graph_validation import require_valid
    with Session(engine) as session:
        latest=_current_graph(session,bid,revision_id)
        target=session.get(PlanGraphRevision,body.target_revision_id)
        if target is None or target.blueprint_id!=bid:
            raise HTTPException(404,'Target revision not found')
        if target.source_layout_id!=latest.source_layout_id or target.version>=latest.version:
            raise HTTPException(409,'Restore requires an earlier revision from the same source layout')
        try:
            require_valid(CanonicalPlan.model_validate(target.graph))
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
        return _append_graph(session,latest,target.graph,
            {'kind':'restore','target_revision_id':target.id})

class ReconstructionBody(BaseModel):
    max_gap_px: float = 80
    min_support: float = .8


class AcceptReconstructionBody(ReconstructionBody):
    preview_token: str
    candidate_ids: list[str]


def _reconstruction_preview(session: Session, bid: str, revision_id: str, body: ReconstructionBody):
    from hashlib import sha256
    import json
    from .plan_graph import CanonicalPlan
    from .global_reconstruction import propose_reconstruction
    latest=_current_graph(session,bid,revision_id)
    bp=session.get(Blueprint,bid)
    try:
        raw=Path(bp.preview_path).read_bytes()
        with Image.open(io.BytesIO(raw)) as image:
            result=propose_reconstruction(CanonicalPlan.model_validate(latest.graph),image,
                max_gap_px=body.max_gap_px,min_support=body.min_support)
    except (OSError,ValueError) as exc:
        raise HTTPException(422,str(exc)) from exc
    image_sha=sha256(raw).hexdigest()
    token=sha256(json.dumps({'revision':latest.id,'source_sha256':image_sha,
        'max_gap_px':body.max_gap_px,'min_support':body.min_support,
        'result':result},sort_keys=True).encode()).hexdigest()
    return latest,{**result,'saved':False,'revision_id':latest.id,
        'source_sha256':image_sha,'preview_token':token,
        'parameters':{'max_gap_px':body.max_gap_px,'min_support':body.min_support}}


@app.post('/blueprints/{bid}/canonical-plan/revisions/{revision_id}/reconstruction/preview')
def preview_graph_reconstruction(bid: str, revision_id: str, body: ReconstructionBody):
    with Session(engine) as session:
        return _reconstruction_preview(session,bid,revision_id,body)[1]


@app.post('/blueprints/{bid}/canonical-plan/revisions/{revision_id}/reconstruction/accept')
def accept_graph_reconstruction(bid: str, revision_id: str, body: AcceptReconstructionBody):
    from .plan_graph import CanonicalPlan
    from .global_reconstruction import apply_candidates
    with Session(engine) as session:
        latest,preview=_reconstruction_preview(session,bid,revision_id,body)
        if body.preview_token!=preview['preview_token']:
            raise HTTPException(409,'Source image or proposal changed; preview again')
        ids=body.candidate_ids
        available={c['id']:c for c in preview['candidates']}
        if not ids or len(ids)!=len(set(ids)) or not set(ids)<=available.keys():
            raise HTTPException(422,'Select a nonempty set of distinct current candidate IDs')
        chosen=[c for c in preview['candidates'] if c['id'] in ids]
        endpoints=[n for c in chosen for n in (c['start_node_id'],c['end_node_id'])]
        if len(endpoints)!=len(set(endpoints)):
            raise HTTPException(422,'Selected candidates compete for a dangling junction')
        try:
            result=apply_candidates(CanonicalPlan.model_validate(latest.graph),chosen)
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
        return _append_graph(session,latest,result.model_dump(mode='json'),{
            'kind':'accept_reconstruction','source_sha256':preview['source_sha256'],
            'preview_token':preview['preview_token'],'parameters':preview['parameters'],
            'candidates':chosen})


@app.post('/blueprints/{bid}/canonical-plan/revisions/{revision_id}/draft')
def canonical_draft(bid: str, revision_id: str):
    """Project the CURRENT graph into an unsaved main-editor draft."""
    from .plan_graph import CanonicalPlan
    from .graph_adapter import to_geometry
    with Session(engine) as session:
        revision=_current_graph(session,bid,revision_id)
        try:
            geometry=to_geometry(CanonicalPlan.model_validate(revision.graph))
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
        return {'saved':False,'revision_id':revision.id,
                'source_layout_version':revision.source_layout_version,
                'geometry':geometry.model_dump(mode='json')}
