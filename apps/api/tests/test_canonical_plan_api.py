"""API contract: immutable graph revisions never overwrite saved legacy drafts."""
import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine, select
from app import main
from app.geometry import Geometry, Wall, Pt
from app.models import Project, Blueprint, Layout, PlanGraphRevision
from app.graph_operations import GraphOperation


def test_canonical_revision_creation_atomic_edits_and_stale_guard(monkeypatch):
    database=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    SQLModel.metadata.create_all(database)
    monkeypatch.setattr(main,'engine',database)
    g=Geometry(width_px=300,height_px=200,walls=[
       Wall(id='wall-a',start=Pt(x=20,y=100),end=Pt(x=200,y=100))])
    with Session(database) as session:
        p=Project(title='Canonical graph regression')
        session.add(p);session.flush()
        bp=Blueprint(project_id=p.id,filename='sample.png',local_path='none',
                     preview_path='none',width=300,height=200)
        session.add(bp);session.flush()
        saved=Layout(blueprint_id=bp.id,version=1,geometry=g.model_dump())
        session.add(saved);session.commit()
        bid=bp.id
    preview=main.preview_canonical_plan(bid)
    assert preview['saved'] is False
    assert preview['source_layout_version']==1
    with Session(database) as session:
        assert session.exec(select(PlanGraphRevision)).first() is None
    initial=main.create_canonical_revision(bid,main.CreateCanonicalPlanBody(expected_layout_version=1))
    assert initial.version==1
    assert initial.operation['kind']=='import_legacy'
    assert initial.graph['walls'][0]['id']=='wall-a'
    node=initial.graph['nodes'][0]
    updated=main.edit_canonical_revision(bid,initial.id,{
        'kind':'move_junction','node_id':node['id'],
        'point':{'x':node['point']['x']+5,'y':node['point']['y']+5}})
    assert updated.version==2 and updated.parent_revision_id==initial.id
    assert updated.graph != initial.graph
    with Session(database) as session:
        saved=session.exec(select(Layout).where(Layout.blueprint_id==bid)).one()
        assert saved.version==1
        assert saved.geometry==g.model_dump()
        assert len(session.exec(select(PlanGraphRevision)).all())==2
    with pytest.raises(HTTPException) as exc:
        main.edit_canonical_revision(bid,initial.id,{'kind':'remove_wall','wall_id':'wall-a'})
    assert exc.value.status_code==409
    with pytest.raises(HTTPException) as exc:
        main.edit_canonical_revision(bid,updated.id,{
            'kind':'move_junction','node_id':node['id'],'point':{'x':-100,'y':0}})
    assert exc.value.status_code==422
    with Session(database) as session:
        assert len(session.exec(select(PlanGraphRevision)).all())==2
    latest=main.latest_canonical_revision(bid)
    assert latest['revision'].id==updated.id
    assert latest['stale'] is False
    with pytest.raises(HTTPException) as exc:
        main.create_canonical_revision(bid,main.CreateCanonicalPlanBody(expected_layout_version=1))
    assert exc.value.status_code==409


def test_canonical_revision_rejects_layout_drift(monkeypatch):
    database=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    SQLModel.metadata.create_all(database)
    monkeypatch.setattr(main,'engine',database)
    g=Geometry(width_px=200,height_px=200,walls=[
        Wall(id='a',start=Pt(x=20,y=20),end=Pt(x=180,y=20))])
    with Session(database) as session:
        p=Project(title='Drift')
        session.add(p);session.flush()
        bp=Blueprint(project_id=p.id,filename='test.png',local_path='none',
                     preview_path='none',width=200,height=200)
        session.add(bp);session.flush()
        session.add(Layout(blueprint_id=bp.id,version=1,geometry=g.model_dump()))
        session.commit();bid=bp.id
    initial=main.create_canonical_revision(bid,main.CreateCanonicalPlanBody(expected_layout_version=1))
    with Session(database) as session:
        session.add(Layout(blueprint_id=bid,version=2,geometry=g.model_dump()))
        session.commit()
    with pytest.raises(HTTPException) as exc:
        main.edit_canonical_revision(bid,initial.id,{'kind':'remove_wall','wall_id':'a'})
    assert exc.value.status_code==409
    assert main.latest_canonical_revision(bid)['stale'] is True
