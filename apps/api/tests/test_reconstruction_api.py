import pytest
from sqlmodel import Session, select
from app.models import Blueprint, PlanGraphRevision, Layout
from test_graph_workspace import workspace
from test_global_reconstruction import broken_loop, raster

@pytest.fixture
def reconstruction(workspace,tmp_path):
    c,db,bid,root,initial,g=workspace
    path=tmp_path/'source.png';raster([[(80,20),(120,20)]]).save(path)
    with Session(db) as s:
        bp=s.get(Blueprint,bid);bp.preview_path=str(path);s.add(bp)
        row=s.get(PlanGraphRevision,initial['id']);row.graph=broken_loop().model_dump();s.add(row);s.commit()
    base=f"{root}/{initial['id']}/reconstruction"
    yield c,db,bid,root,initial,base,path


def count(db):
    with Session(db) as s:return len(s.exec(select(PlanGraphRevision)).all())


def test_preview_accept_and_undo_are_source_bound_and_atomic(reconstruction):
    c,db,bid,root,initial,base,path=reconstruction
    with Session(db) as s:
        source=s.get(PlanGraphRevision,initial['id']).graph
        layout=s.exec(select(Layout)).one().geometry
    response=c.post(base+'/preview',json={})
    assert response.status_code==200
    p=response.json()
    assert p['saved'] is False and len(p['source_sha256'])==64
    assert count(db)==1
    payload={'preview_token':p['preview_token'],'candidate_ids':p['recommended_ids']}
    accepted=c.post(base+'/accept',json=payload)
    assert accepted.status_code==200
    row=accepted.json()
    assert row['version']==2
    assert len(row['graph']['rooms'])==1 and not row['graph']['rooms'][0]['verified']
    assert row['operation']['source_sha256']==p['source_sha256']
    assert row['graph']['openings']==source['openings']
    assert c.post(base+'/accept',json=payload).status_code==409
    restored=c.post(f"{root}/{row['id']}/restore",json={'target_revision_id':initial['id']})
    assert restored.status_code==200 and restored.json()['graph']==source
    with Session(db) as s:
        assert s.exec(select(Layout)).one().geometry==layout
    assert count(db)==3


@pytest.mark.parametrize('selection',[[],['unknown'],['duplicate','duplicate']])
def test_invalid_selection_does_not_write(reconstruction,selection):
    c,db,bid,root,initial,base,path=reconstruction
    p=c.post(base+'/preview',json={}).json()
    assert c.post(base+'/accept',json={'preview_token':p['preview_token'],'candidate_ids':selection}).status_code==422
    assert count(db)==1


def test_image_drift_and_parameter_drift_reject_old_preview(reconstruction):
    c,db,bid,root,initial,base,path=reconstruction
    p=c.post(base+'/preview',json={}).json()
    payload={'preview_token':p['preview_token'],'candidate_ids':p['recommended_ids']}
    assert c.post(base+'/accept',json={**payload,'min_support':.9}).status_code==409
    raster([]).save(path)
    assert c.post(base+'/accept',json=payload).status_code==409
    assert count(db)==1


def test_layout_drift_rejects_preview_and_accept(reconstruction):
    c,db,bid,root,initial,base,path=reconstruction
    p=c.post(base+'/preview',json={}).json()
    with Session(db) as s:
        old=s.exec(select(Layout)).one()
        s.add(Layout(blueprint_id=bid,version=2,geometry=old.geometry));s.commit()
    assert c.post(base+'/preview',json={}).status_code==409
    assert c.post(base+'/accept',json={'preview_token':p['preview_token'],'candidate_ids':p['recommended_ids']}).status_code==409
    assert count(db)==1
