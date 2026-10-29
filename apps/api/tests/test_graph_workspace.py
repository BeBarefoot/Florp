"""Graph workspace HTTP contracts and failure atomicity."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select
from app import main
from app.geometry import Geometry, Wall, Opening, Pt
from app.models import Project, Blueprint, Layout, PlanGraphRevision

@pytest.fixture
def workspace(monkeypatch):
    db=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    SQLModel.metadata.create_all(db)
    monkeypatch.setattr(main,'engine',db)
    g=Geometry(width_px=300,height_px=200,px_per_meter=50,scale_source='user_confirmed',walls=[
        Wall(id='a',start=Pt(x=20,y=20),end=Pt(x=220,y=20)),
        Wall(id='b',start=Pt(x=220,y=20),end=Pt(x=220,y=180))],openings=[
        Opening(id='window',kind='window',wall_id='a',offset_m=1,width_m=1,height_m=1,sill_m=1)])
    with Session(db) as s:
        p=Project(title='Workspace');s.add(p);s.flush()
        bp=Blueprint(project_id=p.id,filename='test.png',local_path='none',preview_path='none',width=300,height=200)
        s.add(bp);s.flush();bid=bp.id
        s.add(Layout(blueprint_id=bid,version=1,geometry=g.model_dump()));s.commit()
    with TestClient(main.app) as c:
        root=f'/blueprints/{bid}/canonical-plan/revisions'
        initial=c.post(root,json={'expected_layout_version':1}).json()
        yield c,db,bid,root,initial,g
    db.dispose()


def test_projection_move_restore_preserves_history_and_windows(workspace):
    c,db,bid,root,initial,g=workspace
    projection=c.get(f"{root}/{initial['id']}/geometry")
    assert projection.status_code==200
    assert projection.json()['geometry']['openings']==[o.model_dump() for o in g.openings]
    assert projection.json()['geometry']['rooms']==[]
    junction=next(n for n in initial['graph']['nodes'] if n['point']=={'x':220.,'y':20.})
    response=c.post(f"{root}/{initial['id']}/operations",json={
        'kind':'move_junction','node_id':junction['id'],'point':{'x':230,'y':20}})
    assert response.status_code==200
    edited=response.json()
    projected=c.get(f"{root}/{edited['id']}/geometry").json()['geometry']
    assert projected['walls'][0]['end']==projected['walls'][1]['start']=={'x':230.,'y':20.}
    assert projected['openings']==projection.json()['geometry']['openings']
    restored=c.post(f"{root}/{edited['id']}/restore",json={'target_revision_id':initial['id']})
    assert restored.status_code==200
    assert restored.json()['graph']==initial['graph']
    assert restored.json()['parent_revision_id']==edited['id']
    with Session(db) as s:
        assert len(s.exec(select(PlanGraphRevision)).all())==3
        assert s.get(PlanGraphRevision,initial['id']).graph==initial['graph']
        assert s.exec(select(Layout)).one().geometry==g.model_dump()
    assert c.post(f"{root}/{edited['id']}/restore",json={'target_revision_id':initial['id']}).status_code==409


def test_restore_rejects_foreign_target_and_source_drift(workspace):
    c,db,bid,root,initial,g=workspace
    edited=c.post(f"{root}/{initial['id']}/operations",json={'kind':'remove_wall','wall_id':'b'}).json()
    assert c.post(f"{root}/{edited['id']}/restore",json={'target_revision_id':'missing'}).status_code==404
    assert c.get(f"/blueprints/other/canonical-plan/revisions/{initial['id']}/geometry").status_code==404
    with Session(db) as s:
        foreign=PlanGraphRevision(blueprint_id='other',source_layout_id='other',source_layout_version=1,graph=initial['graph'],version=1)
        s.add(foreign);s.commit();fid=foreign.id
    assert c.post(f"{root}/{edited['id']}/restore",json={'target_revision_id':fid}).status_code==404
    with Session(db) as s:
        s.add(Layout(blueprint_id=bid,version=2,geometry=g.model_dump()));s.commit()
    assert c.post(f"{root}/{edited['id']}/restore",json={'target_revision_id':initial['id']}).status_code==409
    fresh=c.post(root,json={'expected_layout_version':2}).json()
    assert c.post(f"{root}/{fresh['id']}/restore",json={'target_revision_id':initial['id']}).status_code==409
    with Session(db) as s:
        assert len(s.exec(select(PlanGraphRevision).where(PlanGraphRevision.blueprint_id==bid)).all())==3


def test_projection_refuses_unresolved_opening(workspace):
    c,db,bid,root,initial,g=workspace
    with Session(db) as s:
        row=s.get(PlanGraphRevision,initial['id'])
        graph=dict(row.graph);graph['pending_openings']=[g.openings[0].model_dump()]
        row.graph=graph;s.add(row);s.commit()
    response=c.get(f"{root}/{initial['id']}/geometry")
    assert response.status_code==422
    assert 'pending' in response.json()['detail']


def test_main_draft_projection_is_read_only_and_rejects_stale_graph(workspace):
    c,db,bid,root,initial,g=workspace
    projected=c.post(f"{root}/{initial['id']}/draft")
    assert projected.status_code==200
    assert projected.json()['saved'] is False
    assert projected.json()['geometry']['openings']==[o.model_dump() for o in g.openings]
    with Session(db) as s:
        assert len(s.exec(select(Layout)).all())==1
        assert len(s.exec(select(PlanGraphRevision)).all())==1
    edited=c.post(f"{root}/{initial['id']}/operations",json={'kind':'remove_wall','wall_id':'b'}).json()
    assert c.post(f"{root}/{initial['id']}/draft").status_code==409
    with Session(db) as s:
        s.add(Layout(blueprint_id=bid,version=2,geometry=g.model_dump()));s.commit()
    assert c.post(f"{root}/{edited['id']}/draft").status_code==409


def test_opening_review_reassociates_stale_model_host(workspace):
    c,db,bid,root,initial,g=workspace
    hint={'candidate_id':'detected-window','kind':'window','x1':50,'x2':70,'y1':16,'y2':24,
          'source_confidence':.9,'wall_id':'deleted-proposal-wall','fraction':.9,'reason':'old match'}
    # Use clear geometry so the existing fixture window does not overlap the hint.
    g.openings=[]
    response=c.post(f'/blueprints/{bid}/opening-review/draft',json={'geometry':g.model_dump(),'hint':hint})
    assert response.status_code==200
    result=response.json()
    assert result['status']=='added'
    assert result['hint']['wall_id']=='a'
    assert result['geometry']['openings'][0]['wall_id']=='a'
    hint.update(x1=50,x2=70,y1=150,y2=158,wall_id='a')
    unresolved=c.post(f'/blueprints/{bid}/opening-review/draft',json={'geometry':g.model_dump(),'hint':hint}).json()
    assert unresolved['status']=='unresolved'
    assert unresolved['geometry']['openings']==[]


def test_real_34_wall_fixture_can_initialize_and_project_without_losing_fragments(workspace):
    import json
    from pathlib import Path
    c,db,bid,root,initial,g=workspace
    data=json.loads((Path(__file__).parent/'fixtures/reviewed_34_wall_snapshot.json').read_text())
    real=Geometry(width_px=data['width_px'],height_px=data['height_px'],walls=[
        Wall(id=wid,start=Pt(x=x1,y=y1),end=Pt(x=x2,y=y2)) for wid,x1,y1,x2,y2 in data['walls']])
    with Session(db) as s:
        s.add(Layout(blueprint_id=bid,version=2,geometry=real.model_dump()));s.commit()
    response=c.post(root,json={'expected_layout_version':2})
    assert response.status_code==200
    revision=response.json()
    assert {w['source_wall_id'] for w in revision['graph']['walls']}=={w.id for w in real.walls}
    projection=c.post(f"{root}/{revision['id']}/draft")
    assert projection.status_code==200
    assert len(projection.json()['geometry']['walls'])==len(revision['graph']['walls'])
    assert projection.json()['geometry']['rooms']==[]
    with Session(db) as s:
        assert len(s.exec(select(Layout)).all())==2
        assert s.exec(select(Layout).where(Layout.version==2)).one().geometry==real.model_dump()


def test_legacy_placeholder_hidden_on_read_and_cleaned_on_save_without_rewriting_history(workspace):
    from app.geometry import fallback_geometry
    c,db,bid,root,initial,g=workspace
    legacy=fallback_geometry(300,200)
    legacy.walls.append(Wall(id='real-wall',start=Pt(x=50,y=50),end=Pt(x=220,y=50)))
    with Session(db) as s:
        row=Layout(blueprint_id=bid,version=2,verified=True,geometry=legacy.model_dump());s.add(row);s.commit();old_id=row.id
    response=c.get(f'/blueprints/{bid}/layout')
    assert [w['id'] for w in response.json()['geometry']['walls']]==['real-wall']
    assert response.json()['geometry']['rooms']==[]
    assert response.json()['verified'] is False
    saved=c.post(f'/blueprints/{bid}/layout',json={'geometry':response.json()['geometry']})
    assert saved.status_code==200 and len(saved.json()['geometry']['walls'])==1
    with Session(db) as s:
        assert len(s.get(Layout,old_id).geometry['walls'])==5
        assert s.get(Layout,old_id).verified is True


def test_pending_preview_and_explicit_resolution(workspace):
    c,db,bid,root,initial,g=workspace
    with Session(db) as s:
        row=s.get(PlanGraphRevision,initial['id']);graph=dict(row.graph)
        pending=g.openings[0].model_dump();pending['id']='unmatched'
        graph['pending_openings']=[pending];row.graph=graph;s.add(row);s.commit()
    url=f"{root}/{initial['id']}"
    assert c.get(url+'/geometry').status_code==422
    assert c.get(url+'/geometry?draft_preview=true').status_code==200
    assert c.post(url+'/draft').status_code==422
    resolved=c.post(url+'/resolve-opening',json={'opening_id':'unmatched','reason':'False duplicate detection','replacement':None})
    assert resolved.status_code==200,resolved.text
    assert resolved.json()['operation']['original']['id']=='unmatched'
    assert resolved.json()['graph']['pending_openings']==[]
    assert c.post(f"{root}/{resolved.json()['id']}/draft").status_code==200
