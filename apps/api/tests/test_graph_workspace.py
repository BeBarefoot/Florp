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
