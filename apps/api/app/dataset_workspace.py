"""Durable, source-bound annotation revisions and reproducible dataset exports."""
from pathlib import Path
import hashlib, json, sqlite3, io, zipfile
from uuid import uuid4
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, UploadFile, File
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

def root():
    p=Path(settings.storage_path)/'dataset';p.mkdir(parents=True,exist_ok=True);return p

def db():
    c=sqlite3.connect(root()/'workspace.sqlite',timeout=30)
    c.row_factory=sqlite3.Row
    c.execute('CREATE TABLE IF NOT EXISTS revisions (case_id TEXT, revision INTEGER, payload TEXT NOT NULL, PRIMARY KEY(case_id,revision))')
    c.commit();return c

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
def edit_case(bid:str,body:Edit):
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
        record={**body.model_dump(),**source,'revision':body.expected_revision+1,'saved_at':datetime.now(timezone.utc).isoformat(),'status':'ready' if ready else 'draft'}
        c.execute('INSERT INTO revisions VALUES (?,?,?)',(bid,record['revision'],json.dumps(record)))
        c.commit()
    return record

def archive(include_dataset=False):
    from .main import engine
    from .models import Blueprint,Layout,PlanGraphRevision,FusionCandidateReview,ExtractionEvaluation
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
                records={table.__name__:[r.model_dump(mode='json') for r in s.exec(select(table).where(table.blueprint_id==bp.id)).all()] for table in (Layout,PlanGraphRevision,FusionCandidateReview,ExtractionEvaluation)}
                records['annotations']=[json.loads(r[0]) for r in c.execute('SELECT payload FROM revisions WHERE case_id=? ORDER BY revision',(bp.id,))]
                records['blueprint']=bp.model_dump(mode='json');put(base+'/history.json',json.dumps(records))
            if ann:
                put(base+'/annotation.json',json.dumps(ann))
                if include_dataset:
                    label={k:ann[k] for k in ('width_px','height_px','objects')}
                    label.update(independently_reviewed=True,annotation_complete=True,reviewer=ann['independent_reviewer'])
                    put(base+'/training.json',json.dumps(label))
                    manifest['cases'].append(dict(id=bp.id,group_id=ann['group_id'],split=ann['split'],image=base+'/source.png',annotation=base+'/training.json',source_sha256=source['source_sha256'],usage_rights_confirmed=True))
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
        record=json.loads(p.read_text());record.pop('checkpoint',None);record.pop('dataset',None);records.append(record)
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
    from .models import Blueprint,Project,Layout,PlanGraphRevision,FusionCandidateReview,ExtractionEvaluation
    from sqlmodel import Session
    import re, shutil
    raw=await file.read(256*1024*1024+1)
    if len(raw)>256*1024*1024:raise HTTPException(413,'Archive exceeds 256 MiB')
    folders=[]
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names=z.namelist()
            if len(names)!=len(set(names)) or sum(i.file_size for i in z.infolist())>512*1024*1024:raise ValueError('Duplicate entries or archive too large')
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
                tables={table:[table.model_validate(r) for r in data.get(table.__name__,[])] for table in (Layout,PlanGraphRevision,FusionCandidateReview,ExtractionEvaluation)}
                if any(row.blueprint_id!=bp.id for rows in tables.values() for row in rows):raise ValueError('History case mismatch')
                validated.append((bp,base,source,data,tables))
            with Session(engine) as s, db() as c:
                c.execute('BEGIN IMMEDIATE')
                for bp,base,source,data,tables in validated:
                    if s.get(Blueprint,bp.id) or latest(c,bp.id):raise ValueError('Case already exists; restore into a clean installation')
                    if not s.get(Project,bp.project_id):s.add(Project(id=bp.project_id,title='Restored dataset'));s.flush()
                    folder=Path(settings.storage_path)/bp.id
                    if folder.exists():raise ValueError('Case storage already exists')
                    folder.mkdir();folders.append(folder)
                    (folder/'preview.png').write_bytes(source);(folder/'original.bin').write_bytes(z.read(base+'/original'))
                    bp.preview_path=str(folder/'preview.png');bp.local_path=str(folder/'original.bin');s.add(bp);s.flush()
                    for rows in tables.values():
                        for row in rows:s.add(row)
                    for ann in data['annotations']:c.execute('INSERT INTO revisions VALUES (?,?,?)',(bp.id,ann['revision'],json.dumps(ann)))
                s.flush();s.commit();c.commit()
        return {'restored_cases':len(validated)}
    except (ValueError,KeyError,OSError,zipfile.BadZipFile) as e:
        for p in folders:shutil.rmtree(p,ignore_errors=True)
        raise HTTPException(422,str(e)) from e
