import io,json,zipfile
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlmodel import SQLModel,Session,create_engine
from sqlalchemy.pool import StaticPool
from app import main
from app.config import settings
from app.models import Project,Blueprint

@pytest.fixture
def workspace(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'storage_path',str(tmp_path))
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    SQLModel.metadata.create_all(engine);monkeypatch.setattr(main,'engine',engine)
    ids=[]
    with Session(engine) as s:
        p=Project(title='Dataset');s.add(p);s.flush()
        for i in range(3):
            f=tmp_path/f'{i}.png';Image.new('RGB',(100,80),(255,i,255)).save(f)
            bp=Blueprint(project_id=p.id,filename=f.name,local_path=str(f),preview_path=str(f),width=100,height=80);s.add(bp);s.flush();ids.append(bp.id)
        s.commit()
    yield TestClient(main.app),ids
    engine.dispose()

def body(group='building',split='train'):
    return dict(expected_revision=0,group_id=group,split=split,reviewer='a',independent_reviewer='b',complete=True,rights_confirmed=True,objects=[dict(kind='wall',polygon=[[0,0],[40,0],[40,10],[0,10]])])

def test_durable_revision_conflict_backup_and_snapshot(workspace):
    c,ids=workspace
    for i,bid in enumerate(ids):
        assert c.put('/dataset/cases/'+bid,json=body(str(i),['train','val','test'][i])).status_code==200
    assert c.put('/dataset/cases/'+ids[0],json=body()).status_code==409
    assert c.get('/dataset/cases/'+ids[0]).json()['annotation']['revision']==1
    snap=c.post('/dataset/snapshots');assert snap.status_code==200,snap.text
    assert snap.json()['case_count']==3
    raw=c.get('/dataset/backup');assert raw.status_code==200
    with zipfile.ZipFile(io.BytesIO(raw.content)) as z:
        history=json.loads(z.read('cases/'+ids[0]+'/history.json'))
        assert history['annotations'][0]['revision']==1
        assert 'checksums.json' in z.namelist()

def test_no_false_gold_and_leakage(workspace):
    c,ids=workspace
    b=body();b['independent_reviewer']='a'
    assert c.put('/dataset/cases/'+ids[0],json=b).status_code==422
    for i,bid in enumerate(ids):assert c.put('/dataset/cases/'+bid,json=body('same',['train','val','test'][i])).status_code==200
    assert c.post('/dataset/snapshots').status_code==422

def test_invalid_masks_and_drafts(workspace):
    c,ids=workspace;b=body();b['objects'][0]['polygon'][0]=[-1,0]
    assert c.put('/dataset/cases/'+ids[0],json=b).status_code==422
    b=body();b.update(complete=False,objects=[],reviewer='',independent_reviewer='')
    assert c.put('/dataset/cases/'+ids[0],json=b).status_code==200
    assert c.get('/dataset/cases/'+ids[0]).json()['annotation']['status']=='draft'

def test_training_preflight_and_download(workspace,monkeypatch):
    c,ids=workspace
    for i,bid in enumerate(ids):assert c.put('/dataset/cases/'+bid,json=body(str(i),['train','val','test'][i])).status_code==200
    sid=c.post('/dataset/snapshots').json()['id']
    assert c.get('/dataset/snapshots/'+sid+'/download').status_code==200
    assert c.post('/dataset/runs',json={'snapshot_id':sid,'device':'cuda'}).status_code==422
    monkeypatch.setattr(settings,'wall_segmentation_weights','')
    assert c.post('/dataset/runs',json={'snapshot_id':sid}).status_code==422
    assert c.get('/dataset/runs').json()==[]

def test_restore_checksum_and_conflict(workspace):
    c,ids=workspace
    assert c.put('/dataset/cases/'+ids[0],json=body()).status_code==200
    raw=c.get('/dataset/backup').content
    assert c.post('/dataset/restore',files={'file':('backup.zip',raw,'application/zip')}).status_code==422
    stream=io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as source,zipfile.ZipFile(stream,'w') as z:
        for name in source.namelist():z.writestr(name,b'corrupt' if name.endswith('/source.png') else source.read(name))
    assert c.post('/dataset/restore',files={'file':('backup.zip',stream.getvalue(),'application/zip')}).status_code==422

def test_restore_on_clean_install(workspace,tmp_path,monkeypatch):
    c,ids=workspace
    assert c.put('/dataset/cases/'+ids[0],json=body()).status_code==200
    raw=c.get('/dataset/backup').content
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    SQLModel.metadata.create_all(engine);monkeypatch.setattr(main,'engine',engine)
    monkeypatch.setattr(settings,'storage_path',str(tmp_path/'clean'))
    response=c.post('/dataset/restore',files={'file':('backup.zip',raw,'application/zip')})
    assert response.status_code==200,response.text
    assert response.json()['restored_cases']==3
    assert c.get('/dataset/cases/'+ids[0]).json()['annotation']['revision']==1
    assert len(c.get('/dataset/cases').json())==3
    engine.dispose()

def test_worker_records_failure_before_model_load(tmp_path):
    import hashlib
    from app.training_worker import execute
    run=tmp_path/'runs'/'one';run.mkdir(parents=True)
    weights=tmp_path/'weights.pt';weights.write_bytes(b'changed')
    job={'checkpoint':str(weights),'checkpoint_sha256':hashlib.sha256(b'original').hexdigest()}
    (run/'job.json').write_text(json.dumps(job))
    with pytest.raises(ValueError,match='Checkpoint changed'):execute(run)
    assert json.loads((run/'job.json').read_text())['status']=='failed'

def test_pdf_pages_are_retry_safe_and_originals_preserved(workspace,monkeypatch):
    import fitz
    from types import SimpleNamespace
    c,ids=workspace
    monkeypatch.setattr(main,'inspect_plan',lambda *args:SimpleNamespace(automatic_scale=None))
    pdf=fitz.open();pdf.new_page(width=100,height=80);pdf.new_page(width=100,height=80);raw=pdf.tobytes();pdf.close()
    response=c.post('/dataset/import',files={'file':('two.pdf',raw,'application/pdf')})
    assert response.status_code==200,response.text
    assert response.json()['pages']==2
    repeat=c.post('/dataset/import',files={'file':('two.pdf',raw,'application/pdf')})
    assert repeat.json()['case_ids']==response.json()['case_ids']
    assert len(c.get('/dataset/cases').json())==5


def test_35_case_annotation_campaign(workspace,monkeypatch):
    from types import SimpleNamespace
    c,existing=workspace
    monkeypatch.setattr(main,'inspect_plan',lambda *args:SimpleNamespace(automatic_scale=None))
    for i in range(35):
        image=io.BytesIO();Image.new('RGB',(100,80),(i,100,200)).save(image,format='PNG')
        response=c.post('/dataset/import',files={'file':(str(i)+'.png',image.getvalue(),'image/png')})
        assert response.status_code==200,response.text
        bid=response.json()['case_ids'][0]
        split='train' if i<20 else ('val' if i<25 else 'test')
        assert c.put('/dataset/cases/'+bid,json=body('group-'+str(i),split)).status_code==200
    snapshot=c.post('/dataset/snapshots')
    assert snapshot.status_code==200,snapshot.text
    assert snapshot.json()['case_count']==35


def test_cancel_and_resume_requires_optimizer_checkpoint(workspace,tmp_path):
    from app.dataset_workspace import root
    c,_=workspace;rid='a'*32;folder=root()/'runs'/rid;folder.mkdir(parents=True)
    (folder/'job.json').write_text(json.dumps({'id':rid,'status':'failed','created_at':'2026-10-29'}))
    assert c.post('/dataset/runs/'+rid+'/cancel').status_code==200
    assert (folder/'cancel').exists()
    assert c.post('/dataset/runs/'+rid+'/resume').status_code==422

def test_seed_is_preserved_and_cannot_overwrite_corrections(workspace,monkeypatch):
    import numpy as np
    from app import yytsi_raster,pretrained_detector
    c,ids=workspace
    mask=np.zeros((80,100),dtype=np.uint8);mask[10:20,10:60]=255
    monkeypatch.setattr(yytsi_raster,'predict_yytsi_raster',lambda *args:(mask,{'provider':'fixture'}))
    monkeypatch.setattr(pretrained_detector,'detect_objects',lambda *args:pretrained_detector.DetectorResult(image_width=100,image_height=80,boxes=[]))
    response=c.post('/dataset/cases/'+ids[0]+'/seed',json={'expected_revision':0})
    assert response.status_code==200,response.text
    assert response.json()['annotation']['complete'] is False
    assert response.json()['annotation']['objects'][0]['kind']=='wall'
    assert c.post('/dataset/cases/'+ids[0]+'/seed',json={'expected_revision':1}).status_code==409

def test_full_workspace_artifacts_restore_portably(workspace,tmp_path,monkeypatch):
    from app.dataset_workspace import root
    from app.training_dataset import verify_dataset
    c,ids=workspace
    for i,bid in enumerate(ids):assert c.put('/dataset/cases/'+bid,json=body(str(i),['train','val','test'][i])).status_code==200
    sid=c.post('/dataset/snapshots').json()['id']
    run=root()/'runs'/('b'*32);run.mkdir(parents=True)
    initial=tmp_path/'initial.pt';initial.write_bytes(b'fixture-checkpoint')
    (run/'job.json').write_text(json.dumps({'id':'b'*32,'snapshot_id':sid,'status':'running','created_at':'2026-10-29','checkpoint':str(initial),'dataset':str(root()/'snapshots'/sid)}))
    (run/'output'/'weights').mkdir(parents=True);(run/'output'/'weights'/'last.pt').write_bytes(b'optimizer fixture')
    raw=c.get('/dataset/backup').content
    clean=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);SQLModel.metadata.create_all(clean)
    monkeypatch.setattr(main,'engine',clean);monkeypatch.setattr(settings,'storage_path',str(tmp_path/'restored'))
    restored=c.post('/dataset/restore',files={'file':('backup.zip',raw,'application/zip')})
    assert restored.status_code==200,restored.text
    verify_dataset(root()/'snapshots'/sid)
    job=json.loads((root()/'runs'/('b'*32)/'job.json').read_text())
    assert job['status']=='interrupted'
    assert job['checkpoint'].startswith(str(tmp_path/'restored'))
    assert c.get('/dataset/runs/'+('b'*32)+'/checkpoint/last').content==b'optimizer fixture'
    clean.dispose()

def test_restore_crash_journal_cleans_only_uncommitted_files(workspace):
    from app.dataset_workspace import root,recover_restore
    c,ids=workspace
    staging=root().parent/'not-committed';staging.mkdir();(staging/'preview.png').write_bytes(b'uncommitted')
    journal=root()/'restore-fixture.json';journal.write_text(json.dumps({'case_ids':['not-committed'],'folders':[str(staging)]}))
    recover_restore();assert not staging.exists();assert not journal.exists()
    committed=root().parent/'committed-artifact';committed.mkdir()
    journal.write_text(json.dumps({'case_ids':[ids[0]],'folders':[str(committed)]}))
    recover_restore();assert committed.exists()

def test_snapshot_explains_zero_ready_without_losing_drafts(workspace):
    c,ids=workspace
    b=body();b.update(complete=False,objects=[],reviewer='',independent_reviewer='')
    assert c.put('/dataset/cases/'+ids[0],json=b).status_code==200
    response=c.post('/dataset/snapshots')
    assert response.status_code==422
    assert 'Only 0 plans are marked Ready' in response.json()['detail']
    assert 'train, validation and test' in response.json()['detail']
    assert c.get('/dataset/cases/'+ids[0]).json()['annotation']['status']=='draft'


def test_snapshot_explains_missing_split(workspace):
    c,ids=workspace
    for i,bid in enumerate(ids):assert c.put('/dataset/cases/'+bid,json=body(str(i),'train')).status_code==200
    response=c.post('/dataset/snapshots')
    assert response.status_code==422
    assert 'validation' not in response.json()['detail'] or 'val' in response.json()['detail']
    assert 'val, test' in response.json()['detail']

def test_reimport_after_project_deletion_recreates_plan(workspace,monkeypatch):
    from types import SimpleNamespace
    c,_=workspace
    monkeypatch.setattr(main,'inspect_plan',lambda *args:SimpleNamespace(automatic_scale=None))
    image=io.BytesIO();Image.new('RGB',(100,80),'blue').save(image,format='PNG');raw=image.getvalue()
    def send():return c.post('/dataset/import',files={'file':('plan.png',raw,'image/png')})
    first=send();assert first.status_code==200,first.text
    first_id=first.json()['case_ids'][0]
    project=next(case['project_id'] for case in c.get('/dataset/cases').json() if case['id']==first_id)
    assert c.delete('/projects/'+project).status_code==200
    again=send();assert again.status_code==200,again.text
    second_id=again.json()['case_ids'][0]
    assert second_id!=first_id
    assert any(case['id']==second_id for case in c.get('/dataset/cases').json())
    assert send().json()['case_ids']==[second_id]
