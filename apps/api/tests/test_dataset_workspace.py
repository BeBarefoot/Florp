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
