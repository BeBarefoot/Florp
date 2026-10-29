"""Durable, source-bound annotation revisions and reproducible dataset exports."""
from pathlib import Path
import hashlib, json, sqlite3, io, zipfile
from uuid import uuid4
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import Response
from pydantic import BaseModel, Field
from PIL import Image
from .config import settings
from .training_dataset import Annotation, ObjectMask, prepare

router=APIRouter(prefix='/dataset',tags=['dataset'])
class Edit(BaseModel):
    expected_revision:int=Field(ge=0)
    group_id:str=Field(min_length=1,max_length=200)
    split:str='train'
    reviewer:str=''
    independent_reviewer:str=''
    complete:bool=False
    rights_confirmed:bool=False
    objects:list[ObjectMask]=Field(default_factory=list)
    px_per_meter:float|None=Field(default=None,gt=0,allow_inf_nan=False)

def root():
    p=Path(settings.storage_path)/'dataset';p.mkdir(parents=True,exist_ok=True);return p

class WorkspaceConnection:
    def __init__(self):
        from .main import engine
        self.handle=engine.raw_connection()
        self.connection=self.handle.driver_connection
        self.connection.row_factory=sqlite3.Row
        self.connection.execute('CREATE TABLE IF NOT EXISTS revisions (case_id TEXT, revision INTEGER, payload TEXT NOT NULL, PRIMARY KEY(case_id,revision))')
        self.connection.commit()
    def __enter__(self):return self.connection
    def __exit__(self,kind,value,tb):
        if kind:self.connection.rollback()
        else:self.connection.commit()
        self.handle.close()

def db():
    # Annotation and structural revisions share the application database.
    # Import the former standalone SQLite store once, preserving every revision.
    wrapper=WorkspaceConnection()
    old=root()/'workspace.sqlite'
    if old.exists():
        with sqlite3.connect(old) as previous:
            rows=previous.execute('SELECT case_id,revision,payload FROM revisions').fetchall()
        wrapper.connection.executemany('INSERT OR IGNORE INTO revisions VALUES (?,?,?)',rows)
        wrapper.connection.commit()
        old.rename(old.with_suffix('.sqlite.migrated'))
    return wrapper

def identity(bp):
    p=Path(bp.preview_path);raw=p.read_bytes()
    with Image.open(io.BytesIO(raw)) as im:w,h=im.size
    return dict(source_sha256=hashlib.sha256(raw).hexdigest(),width_px=w,height_px=h)

def latest(c,bid):
    row=c.execute('SELECT payload FROM revisions WHERE case_id=? ORDER BY revision DESC LIMIT 1',(bid,)).fetchone()
    return json.loads(row[0]) if row else None

def blueprint(bid):
    from .main import engine
    from .models import Blueprint
    from sqlmodel import Session
    with Session(engine) as s:bp=s.get(Blueprint,bid)
    if bp is None:raise HTTPException(404,'Plan not found')
    return bp

@router.get('/cases')
def cases():
    from .main import engine
    from .models import Blueprint
    from sqlmodel import Session,select
    with Session(engine) as s:plans=s.exec(select(Blueprint)).all()
    with db() as c:
        return [{ 'id':p.id,'name':p.filename,'project_id':p.project_id,**identity(p),
                  'annotation':latest(c,p.id)} for p in plans]

@router.get('/cases/{bid}')
def get_case(bid:str):
    bp=blueprint(bid)
    with db() as c:r=latest(c,bid)
    return {'id':bid,'name':bp.filename,**identity(bp),'annotation':r}

@router.put('/cases/{bid}')
def edit_case(bid:str,body:Edit,background_tasks:BackgroundTasks=None):
    bp=blueprint(bid);source=identity(bp)
    if body.split not in ('train','val','test'):raise HTTPException(422,'Invalid split')
    # Check draft polygons too; incomplete drafts may legitimately contain no objects.
    for o in body.objects:
        from shapely.geometry import Polygon
        if not Polygon(o.polygon).is_valid or Polygon(o.polygon).area<1 or any(not(0<=x<=source['width_px'] and 0<=y<=source['height_px']) for x,y in o.polygon):
            raise HTTPException(422,'Invalid or out-of-bounds mask')
    ready=body.complete
    if ready:
        if not body.rights_confirmed or not body.reviewer.strip() or not body.independent_reviewer.strip() or body.reviewer.strip()==body.independent_reviewer.strip():
            raise HTTPException(422,'Ready requires rights and two distinct reviewers')
        try:Annotation(**{k:source[k] for k in ('width_px','height_px')},independently_reviewed=True,annotation_complete=True,reviewer=body.independent_reviewer,objects=body.objects)
        except ValueError as e:raise HTTPException(422,str(e)) from e
    with db() as c:
        c.execute('BEGIN IMMEDIATE');old=latest(c,bid)
        if (old['revision'] if old else 0)!=body.expected_revision:raise HTTPException(409,'Annotation changed in another tab. Reload before saving.')
        if old and old['source_sha256']!=source['source_sha256']:raise HTTPException(409,'Source changed; recover the previous annotation before proceeding')
        from .annotation_geometry import reconstruct
        reconstruction=reconstruct([o.model_dump() for o in body.objects],source['width_px'],source['height_px'],body.px_per_meter)
        record={**body.model_dump(),'reconstruction':reconstruction,**source,'revision':body.expected_revision+1,'saved_at':datetime.now(timezone.utc).isoformat(),'status':'ready' if ready else 'draft'}
        c.execute('INSERT INTO revisions VALUES (?,?,?)',(bid,record['revision'],json.dumps(record)))
        c.commit()
    if ready and background_tasks is not None:background_tasks.add_task(automatic_backup)
    return record

def archive(include_dataset=False):
    from .main import engine
    from .models import Blueprint,Layout,PlanGraphRevision,FusionCandidateReview,ExtractionEvaluation,Project,WallAnnotation,ModelWallCorrection,Render
    from sqlmodel import Session,select
    stream=io.BytesIO();manifest={'schema_version':1,'cases':[]};checksums={}
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z, db() as c, Session(engine) as s:
        def put(name,data):
            if isinstance(data,str):data=data.encode()
            z.writestr(name,data);checksums[name]=hashlib.sha256(data).hexdigest()
        for bp in s.exec(select(Blueprint)).all():
            ann=latest(c,bp.id)
            if include_dataset and (not ann or ann['status']!='ready'):continue
            source=identity(bp)
            if include_dataset and source['source_sha256']!=ann['source_sha256']:raise HTTPException(409,'Source changed: '+bp.filename)
            base='cases/'+bp.id
            raw=Path(bp.preview_path).read_bytes();put(base+'/source.png',raw)
            if not include_dataset:
                put(base+'/original',Path(bp.local_path).read_bytes())
                records={table.__name__:[r.model_dump(mode='json') for r in s.exec(select(table).where(table.blueprint_id==bp.id)).all()] for table in (Layout,PlanGraphRevision,FusionCandidateReview,ExtractionEvaluation,WallAnnotation,ModelWallCorrection,Render)}
                records['annotations']=[json.loads(r[0]) for r in c.execute('SELECT payload FROM revisions WHERE case_id=? ORDER BY revision',(bp.id,))]
                records['blueprint']=bp.model_dump(mode='json');records['project']=s.get(Project,bp.project_id).model_dump(mode='json');put(base+'/history.json',json.dumps(records))
            if ann:
                put(base+'/annotation.json',json.dumps(ann))
                if include_dataset:
                    label={k:ann[k] for k in ('width_px','height_px','objects')}
                    label.update(independently_reviewed=True,annotation_complete=True,reviewer=ann['independent_reviewer'])
                    put(base+'/training.json',json.dumps(label))
                    manifest['cases'].append(dict(id=bp.id,group_id=ann['group_id'],split=ann['split'],image=base+'/source.png',annotation=base+'/training.json',source_sha256=source['source_sha256'],usage_rights_confirmed=True))
        if not include_dataset:
            for category in ('predictions','imports','snapshots','runs'):
                for asset in (root()/category).rglob('*'):
                    if asset.is_file() and asset.name not in ('lock','process.lock','training.lock'):
                        put('artifacts/'+str(asset.relative_to(root())),asset.read_bytes())
            for jobfile in (root()/'runs').glob('*/job.json'):
                job=json.loads(jobfile.read_text());initial=Path(job.get('checkpoint',''))
                if initial.is_file():put('artifacts/runs/'+jobfile.parent.name+'/initial.pt',initial.read_bytes())
        put('manifest.json',json.dumps(manifest));put('checksums.json',json.dumps(checksums))
    return stream.getvalue()

@router.get('/backup')
def backup():
    return Response(archive(),media_type='application/zip',headers={'Content-Disposition':'attachment; filename="florp-annotation-backup.zip"'})

@router.post('/snapshots')
def snapshot():
    import tempfile
    # Use the existing strict builder to reject leakage, duplicates and missing splits.
    identifier=uuid4().hex;target=root()/'snapshots'/identifier
    raw=archive(True)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        eligible=json.loads(z.read('manifest.json'))['cases']
    if len(eligible)<3:
        raise HTTPException(422, f'Only {len(eligible)} plans are marked Ready. Review each plan, confirm rights and independent review, then mark it Ready. A snapshot needs at least 3 Ready plans, including one in each split: train, validation and test. Three is only a smoke-test minimum.')
    missing=[split for split in ('train','val','test') if not any(c['split']==split for c in eligible)]
    if missing:
        raise HTTPException(422, 'Ready plans are missing these splits: '+', '.join(missing)+'. Assign at least one Ready plan to each split; keep all plans from the same building in the same split.')
    try:
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:z.extractall(tmp)
            report=prepare(Path(tmp)/'manifest.json',target)
            # Retain full source annotations beside the prepared immutable dataset.
            (target/'source-annotations.zip').write_bytes(raw)
    except ValueError as e:raise HTTPException(422,str(e)) from e
    return {'id':identifier,'case_count':len(report['cases']),'status':'prepared'}

@router.get('/snapshots')
def snapshots():
    p=root()/'snapshots'
    return [{'id':x.name,'case_count':len(json.loads((x/'provenance.json').read_text())['cases'])} for x in sorted(p.glob('*')) if (x/'provenance.json').exists()]

@router.get('/snapshots/{sid}/download')
def download_snapshot(sid:str):
    import re
    if not re.fullmatch('[a-f0-9]{32}',sid):raise HTTPException(404,'Snapshot not found')
    folder=root()/'snapshots'/sid
    if not (folder/'provenance.json').exists():raise HTTPException(404,'Snapshot not found')
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as z:
        for p in folder.rglob('*'):
            if p.is_file():z.write(p,str(p.relative_to(folder)))
    return Response(stream.getvalue(),media_type='application/zip',headers={'Content-Disposition':f'attachment; filename="florp-dataset-{sid}.zip"'})

class TrainRequest(BaseModel):
    snapshot_id:str=Field(pattern='^[a-f0-9]{32}$')
    device:str='cpu'
    epochs:int=Field(default=100,ge=1,le=1000)
    batch:int=Field(default=1,ge=1,le=64)
    seed:int=Field(default=42,ge=0)

@router.post('/runs')
def start_run(body:TrainRequest):
    import subprocess,sys
    from .training_dataset import verify_dataset
    if body.device not in ('cpu','mps'):raise HTTPException(422,'Choose cpu or mps')
    dataset=root()/'snapshots'/body.snapshot_id
    if not dataset.is_dir():raise HTTPException(404,'Dataset snapshot not found')
    weights=Path(settings.wall_segmentation_weights).expanduser()
    if not settings.wall_segmentation_weights or not weights.is_file():raise HTTPException(422,'Configure WALL_SEGMENTATION_WEIGHTS with a trusted local segmentation checkpoint first')
    try:verify_dataset(dataset)
    except ValueError as e:raise HTTPException(422,str(e)) from e
    run_id=uuid4().hex;folder=root()/'runs'/run_id;folder.mkdir(parents=True)
    job={**body.model_dump(),'id':run_id,'status':'queued','checkpoint_sha256':hashlib.sha256(weights.read_bytes()).hexdigest(),'checkpoint':str(weights.resolve()),'dataset':str(dataset.resolve()),'created_at':datetime.now(timezone.utc).isoformat()}
    (folder/'job.json').write_text(json.dumps(job))
    with (folder/'worker.log').open('ab') as log:
        try:subprocess.Popen([sys.executable,'-m','app.training_worker',str(folder.resolve())],stdout=log,stderr=log,start_new_session=True)
        except OSError as e:
            job.update(status='failed',error=str(e));(folder/'job.json').write_text(json.dumps(job));raise HTTPException(500,'Could not start worker') from e
    return {'id':run_id,'status':'queued'}

@router.get('/runs')
def runs():
    records=[]
    for p in (root()/'runs').glob('*/job.json'):
        record=json.loads(p.read_text())
        if record['status'] in ('running','queued'):
            import fcntl,time
            with (p.parent/'process.lock').open('a') as lock:
                try:
                    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    if time.time()-p.stat().st_mtime>30:record['status']='interrupted'
                except BlockingIOError:pass
        record['resumable']=(p.parent/'output'/'weights'/'last.pt').is_file()
        record.pop('checkpoint',None);record.pop('dataset',None);records.append(record)
    return sorted(records,key=lambda r:r['created_at'],reverse=True)

@router.get('/runs/{rid}/log')
def run_log(rid:str):
    import re
    if not re.fullmatch('[a-f0-9]{32}',rid):raise HTTPException(404,'Run not found')
    p=root()/'runs'/rid/'worker.log'
    if not p.exists():raise HTTPException(404,'Run log not found')
    with p.open('rb') as f:
        f.seek(max(0,p.stat().st_size-64000));text=f.read().decode(errors='replace')
    return {'text':text}

@router.post('/restore')
async def restore_archive(file: UploadFile = File(...)):
    """Restore an annotation archive into non-conflicting case IDs; never overwrite."""
    from .main import engine
    from .models import Blueprint,Project,Layout,PlanGraphRevision,FusionCandidateReview,ExtractionEvaluation,WallAnnotation,ModelWallCorrection,Render
    from sqlmodel import Session
    import re, shutil
    raw=await file.read(2048*1024*1024+1)
    if len(raw)>2048*1024*1024:raise HTTPException(413,'Archive exceeds 2 GiB')
    folders=[];journal=None
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names=z.namelist()
            if len(names)!=len(set(names)) or sum(i.file_size for i in z.infolist())>4096*1024*1024:raise ValueError('Duplicate entries or archive too large')
            sums=json.loads(z.read('checksums.json'))
            if set(names)!=(set(sums)|{'checksums.json'}):raise ValueError('Archive inventory mismatch')
            for name,digest in sums.items():
                if name.startswith('/') or '..' in Path(name).parts or hashlib.sha256(z.read(name)).hexdigest()!=digest:raise ValueError('Unsafe path or checksum mismatch')
            histories=[n for n in names if re.fullmatch(r'cases/[a-f0-9-]{36}/history.json',n)]
            if not histories:raise ValueError('No case histories in archive')
            validated=[]
            for name in histories:
                data=json.loads(z.read(name));bp=Blueprint.model_validate(data['blueprint']);base='cases/'+bp.id
                if name!=base+'/history.json':raise ValueError('Case identity mismatch')
                source=z.read(base+'/source.png')
                with Image.open(io.BytesIO(source)) as image:
                    if image.size!=(bp.width,bp.height):raise ValueError('Source dimensions mismatch')
                sha=hashlib.sha256(source).hexdigest()
                for ann in data['annotations']:
                    if ann['source_sha256']!=sha:raise ValueError('Annotation source mismatch')
                    Edit.model_validate({**{k:ann[k] for k in Edit.model_fields if k in ann},'expected_revision':ann['revision']-1})
                tables={table:[table.model_validate(r) for r in data.get(table.__name__,[])] for table in (Layout,PlanGraphRevision,FusionCandidateReview,ExtractionEvaluation,WallAnnotation,ModelWallCorrection,Render)}
                if any(row.blueprint_id!=bp.id for rows in tables.values() for row in rows):raise ValueError('History case mismatch')
                validated.append((bp,base,source,data,tables))
            with db() as c, Session(engine) as preflight:
                for bp,_,_,_,_ in validated:
                    if preflight.get(Blueprint,bp.id) or latest(c,bp.id) or (Path(settings.storage_path)/bp.id).exists():raise ValueError('Case already exists; restore into a clean installation')
            for category in ('predictions','imports','snapshots','runs'):
                destination=root()/category
                if any(n.startswith('artifacts/'+category+'/') for n in names) and destination.exists() and any(destination.iterdir()):raise ValueError('Artifact storage is not empty')
            from .training_worker import atomic_json
            journal=root()/('restore-'+uuid4().hex+'.json')
            planned=[str((Path(settings.storage_path)/bp.id).resolve()) for bp,_,_,_,_ in validated]
            planned += [str((root()/category).resolve()) for category in ('predictions','imports','snapshots','runs') if any(n.startswith('artifacts/'+category+'/') for n in names)]
            atomic_json(journal,{'case_ids':[bp.id for bp,_,_,_,_ in validated],'folders':planned})
            with db():pass
            with Session(engine) as s:
                c=s.connection().connection.driver_connection
                c.execute('BEGIN IMMEDIATE')
                for bp,base,source,data,tables in validated:
                    if s.get(Blueprint,bp.id) or latest(c,bp.id):raise ValueError('Case already exists; restore into a clean installation')
                    if not s.get(Project,bp.project_id):s.add(Project.model_validate(data['project']) if data.get('project') else Project(id=bp.project_id,title='Restored dataset'));s.flush()
                    folder=Path(settings.storage_path)/bp.id
                    if folder.exists():raise ValueError('Case storage already exists')
                    folder.mkdir();folders.append(folder)
                    (folder/'preview.png').write_bytes(source);(folder/'original.bin').write_bytes(z.read(base+'/original'))
                    bp.preview_path=str(folder/'preview.png');bp.local_path=str(folder/'original.bin');s.add(bp);s.flush()
                    for rows in tables.values():
                        for row in rows:s.add(row)
                    for ann in data['annotations']:c.execute('INSERT INTO revisions VALUES (?,?,?)',(bp.id,ann['revision'],json.dumps(ann)))
                for category in ('predictions','imports','snapshots','runs'):
                    names_for_category=[n for n in names if n.startswith('artifacts/'+category+'/')]
                    if not names_for_category:continue
                    destination=root()/category
                    if destination.exists() and any(destination.iterdir()):raise ValueError('Artifact storage is not empty; restore into a clean installation')
                    destination.mkdir(exist_ok=True);folders.append(destination)
                    for name in names_for_category:
                        relative=Path(name).relative_to('artifacts')
                        target=root()/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(name))
                for provenance in (root()/'snapshots').glob('*/provenance.json'):
                    dataset=provenance.parent;report=json.loads(provenance.read_text());yaml=dataset/'dataset.yaml'
                    lines=yaml.read_text().splitlines();lines[0]='path: '+json.dumps(str(dataset.resolve()));yaml.write_text('\n'.join(lines)+'\n')
                    report['original_dataset_yaml_sha256']=report.get('original_dataset_yaml_sha256',report['dataset_yaml_sha256'])
                    report['dataset_yaml_sha256']=hashlib.sha256(yaml.read_bytes()).hexdigest();provenance.write_text(json.dumps(report,indent=2))
                for jobfile in (root()/'runs').glob('*/job.json'):
                    job=json.loads(jobfile.read_text());job['dataset']=str((root()/'snapshots'/job['snapshot_id']).resolve())
                    if (jobfile.parent/'initial.pt').exists():job['checkpoint']=str((jobfile.parent/'initial.pt').resolve())
                    if job['status'] in ('running','queued'):job['status']='interrupted'
                    if job.get('validation_report'):job['validation_report']=Path(job['validation_report']).as_posix()
                    jobfile.write_text(json.dumps(job,indent=2))
                s.flush();s.commit()
        journal.unlink(missing_ok=True)
        return {'restored_cases':len(validated)}
    except (ValueError,KeyError,OSError,zipfile.BadZipFile) as e:
        for p in folders:shutil.rmtree(p,ignore_errors=True)
        if journal:journal.unlink(missing_ok=True)
        raise HTTPException(422,str(e)) from e

def run_folder(rid):
    import re
    if not re.fullmatch('[a-f0-9]{32}',rid):raise HTTPException(404,'Run not found')
    folder=root()/'runs'/rid
    if not (folder/'job.json').exists():raise HTTPException(404,'Run not found')
    return folder

@router.post('/runs/{rid}/cancel')
def cancel_run(rid:str):
    folder=run_folder(rid);(folder/'cancel').touch()
    return {'status':'cancellation_requested','note':'Training stops at the next epoch boundary; a queued run stops before loading.'}

@router.post('/runs/{rid}/resume')
def resume_run(rid:str):
    import subprocess,sys,fcntl
    from .training_worker import atomic_json
    folder=run_folder(rid)
    with (folder/'process.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise HTTPException(409,'Worker still active')
        job=json.loads((folder/'job.json').read_text())
        if job['status']=='completed':raise HTTPException(409,'Completed runs cannot be resumed')
        checkpoint=folder/'output'/'weights'/'last.pt'
        if not checkpoint.is_file():raise HTTPException(422,'No optimizer checkpoint exists yet; start a new run')
        job.update(resume=True,status='queued');job.pop('error',None)
        (folder/'cancel').unlink(missing_ok=True);atomic_json(folder/'job.json',job)
        with (folder/'worker.log').open('ab') as log:
            subprocess.Popen([sys.executable,'-m','app.training_worker',str(folder.resolve())],stdout=log,stderr=log,start_new_session=True)
    return {'id':rid,'status':'queued','resume':'optimizer checkpoint'}

@router.get('/runs/{rid}/checkpoint/{kind}')
def download_checkpoint(rid:str,kind:str):
    from fastapi.responses import FileResponse
    if kind not in ('best','last'):raise HTTPException(404,'Checkpoint not found')
    path=run_folder(rid)/'output'/'weights'/(kind+'.pt')
    if not path.is_file():raise HTTPException(404,'Checkpoint not available yet')
    return FileResponse(path,filename=f'florp-{rid}-{kind}.pt')

@router.post('/import')
async def import_plans(file:UploadFile=File(...)):
    """Retry-safe file import: persist every completed PDF page before proceeding."""
    import fitz,fcntl
    from .main import upload,create_project,CreateProject
    from .training_worker import atomic_json
    raw=await file.read(settings.max_upload_mb*1024*1024+1)
    if len(raw)>settings.max_upload_mb*1024*1024:raise HTTPException(413,'File exceeds upload limit')
    key=hashlib.sha256(raw).hexdigest();folder=root()/'imports'/key;folder.mkdir(parents=True,exist_ok=True)
    with (folder/'lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise HTTPException(409,'This file is already importing; retry later')
        path=folder/'job.json'
        job=json.loads(path.read_text()) if path.exists() else {'pages':{},'project_id':create_project(CreateProject(title='Dataset: '+(file.filename or 'Import'))).id}
        # A cached import is only complete while its corresponding plans exist.
        # Projects can be deleted after import, leaving the resumable job behind.
        from .main import engine
        from .models import Blueprint,Project
        from sqlmodel import Session
        with Session(engine) as session:
            job['pages']={number:bid for number,bid in job['pages'].items() if session.get(Blueprint,bid) is not None}
            project_exists=session.get(Project,job['project_id']) is not None
        if not project_exists:
            job['project_id']=create_project(CreateProject(title='Dataset: '+(file.filename or 'Import'))).id
        atomic_json(path,job)
        (folder/'original').write_bytes(raw)
        pdf=None
        try:
            if raw.startswith(b'%PDF-'):
                pdf=fitz.open(stream=raw,filetype='pdf')
                if len(pdf)>100:raise ValueError('At most 100 pages per PDF')
                count=len(pdf)
            else:count=1
            for i in range(count):
                if str(i) in job['pages']:continue
                if pdf:
                    page=pdf[i]
                    if page.rect.width*page.rect.height*4>45_000_000:raise ValueError('PDF page too large')
                    image=page.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False).tobytes('png')
                else:image=raw
                bp=await upload(job['project_id'],UploadFile(file=io.BytesIO(image),filename=(file.filename or 'plan')+(f' · page {i+1}' if pdf else '')))
                job['pages'][str(i)]=bp.id;atomic_json(path,job)
            return {'case_ids':list(job['pages'].values()),'pages':count,'status':'completed'}
        except (ValueError,RuntimeError) as e:raise HTTPException(422,str(e)) from e
        finally:
            if pdf:pdf.close()

class SeedRequest(BaseModel):
    expected_revision:int=Field(ge=0)

@router.post('/cases/{bid}/seed')
def seed_annotations(bid:str,body:SeedRequest):
    """Capture unchanged model evidence; never replace an existing correction."""
    import cv2,numpy as np
    from shapely.geometry import Polygon
    from shapely.ops import triangulate
    from .wall_segmentation import infer_wall_mask
    from .yytsi_raster import predict_yytsi_raster
    from .pretrained_detector import detect_objects,DetectorUnavailable
    bp=blueprint(bid)
    with db() as c:old=latest(c,bid)
    if old and old['objects']:raise HTTPException(409,'Annotations already exist; original predictions never overwrite corrections')
    if (old['revision'] if old else 0)!=body.expected_revision:raise HTTPException(409,'Annotation revision changed')
    try:
        if settings.wall_segmentation_provider=='yytsi':mask,metadata=predict_yytsi_raster(Path(bp.preview_path),bp.width,bp.height)
        else:
            mask,checkpoint=infer_wall_mask(Path(bp.preview_path),bp.width,bp.height);metadata={'checkpoint':checkpoint,'provider':'ultralytics'}
    except (DetectorUnavailable,ValueError,RuntimeError) as e:raise HTTPException(424,str(e)) from e
    binary=(np.asarray(mask)>0).astype('uint8')*255
    contours,hierarchy=cv2.findContours(binary,cv2.RETR_CCOMP,cv2.CHAIN_APPROX_SIMPLE)
    objects=[]
    if hierarchy is not None:
        for i,contour in enumerate(contours):
            if hierarchy[0][i][3]!=-1 or len(contour)<3:continue
            holes=[];child=hierarchy[0][i][2]
            while child!=-1:
                if len(contours[child])>=3:holes.append(contours[child][:,0,:].tolist())
                child=hierarchy[0][child][0]
            poly=Polygon(contour[:,0,:],holes).buffer(0)
            polygons=list(poly.geoms) if poly.geom_type=='MultiPolygon' else [poly]
            for p in polygons:
                pieces=triangulate(p) if p.interiors else [p]
                for piece in pieces:
                    # Triangles intersecting holes are excluded, never filled as walls.
                    if not p.covers(piece) or piece.area<1:continue
                    objects.append(ObjectMask(kind='wall',polygon=list(piece.exterior.coords)[:-1]))
    detector_error=None;boxes=[]
    try:
        detector=detect_objects(Path(bp.preview_path),bp.width,bp.height);boxes=detector.model_dump()['boxes']
        for box in detector.boxes:
            if box.category not in ('door','window'):continue
            objects.append(ObjectMask(kind=box.category,polygon=[(box.x1,box.y1),(box.x2,box.y1),(box.x2,box.y2),(box.x1,box.y2)]))
    except DetectorUnavailable as e:detector_error=str(e)
    evidence=root()/'predictions'/bid;evidence.mkdir(parents=True,exist_ok=True)
    token=uuid4().hex
    Image.fromarray(binary).save(evidence/(token+'.png'))
    (evidence/(token+'.json')).write_text(json.dumps({**identity(bp),'metadata':metadata,'boxes':boxes,'detector_error':detector_error,'objects':[o.model_dump() for o in objects]}))
    result=edit_case(bid,Edit(expected_revision=body.expected_revision,group_id=old['group_id'] if old else bid,objects=objects))
    return {'annotation':result,'warning':'Model proposals require complete review. Door/window boxes are initial outlines, not verified masks.','detector_error':detector_error}

@router.get('/runs/{rid}/comparison')
def comparison_report(rid:str):
    folder=run_folder(rid);job=json.loads((folder/'job.json').read_text())
    if not job.get('validation_report'):raise HTTPException(404,'Validation comparison is not available yet')
    path=(folder/job['validation_report']).resolve()
    if folder.resolve() not in path.parents:raise HTTPException(422,'Invalid report path')
    return json.loads(path.read_text())


def automatic_backup():
    """Keep two complete review-session backups, replacing files atomically."""
    import fcntl,time
    folder=root()/'backups';folder.mkdir(exist_ok=True)
    with (folder/'lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        target=folder/(str(time.time_ns())+'.zip');temp=target.with_suffix('.tmp')
        try:
            temp.write_bytes(archive());temp.replace(target)
            for old in sorted(folder.glob('*.zip'))[:-2]:old.unlink()
            (folder/'error.txt').unlink(missing_ok=True)
        except Exception as e:
            temp.unlink(missing_ok=True);(folder/'error.txt').write_text(str(e))

@router.get('/backup-status')
def backup_status():
    folder=root()/'backups';archives=sorted(folder.glob('*.zip'))
    error=folder/'error.txt'
    return {'last_backup':archives[-1].name if archives else None,'error':error.read_text() if error.exists() else None,'retained':len(archives)}

def recover_restore():
    """Roll back staged files after a crash unless the DB transaction committed."""
    from .main import engine
    from .models import Blueprint
    from sqlmodel import Session
    import shutil
    storage=Path(settings.storage_path).resolve()
    for journal in root().glob('restore-*.json'):
        record=json.loads(journal.read_text())
        with Session(engine) as s:committed=all(s.get(Blueprint,bid) for bid in record['case_ids'])
        if not committed:
            for name in record['folders']:
                folder=Path(name).resolve()
                if storage in folder.parents and folder!=root().resolve():shutil.rmtree(folder,ignore_errors=True)
        journal.unlink()
