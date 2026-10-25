"""Regression coverage for review workflow and deletion safety."""
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool
from app import main
from app.models import Project, Blueprint, Layout
from app.geometry import Geometry, Wall, Pt, Opening

def test_click_on_proposed_opening_updates_instead_of_409(monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},
                         poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main,'engine',engine)
    with Session(engine) as s:
        project=Project(title='test');s.add(project);s.flush()
        plan=Blueprint(project_id=project.id,filename='test.png',local_path='test.png',
            preview_path='test.png',width=800,height=600)
        s.add(plan);s.flush()
        geometry=Geometry(width_px=800,height_px=600,px_per_meter=100,
            walls=[Wall(id='model-2',start=Pt(x=100,y=200),end=Pt(x=600,y=200))],
            openings=[Opening(id='model-opening-7',wall_id='model-2',kind='window',
                               offset_m=1.1,width_m=1.2,height_m=1.2,sill_m=.9,inferred=True)])
        s.add(Layout(blueprint_id=plan.id,geometry=geometry.model_dump()))
        s.commit()
        plan_id=plan.id
    result=main.propose_opening(plan_id,main.ProvisionalOpeningInput(
        kind='door',wall_id='model-2',fraction=.34))
    parsed=Geometry.model_validate(result.geometry)
    assert len(parsed.openings)==1
    assert parsed.openings[0].kind=='door'
    assert parsed.openings[0].inferred
    with Session(engine) as s:
        assert len(list(s.exec(select(Layout).where(Layout.blueprint_id==plan_id)).all()))==2

def test_delete_project_cleans_dependent_layouts_and_storage(tmp_path,monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},
                         poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main,'engine',engine)
    monkeypatch.setattr(main.settings,'storage_path',str(tmp_path))
    with Session(engine) as s:
        project=Project(title='remove');s.add(project);s.flush()
        plan=Blueprint(project_id=project.id,filename='x',local_path='',
                       preview_path='',width=100,height=100)
        s.add(plan);s.flush()
        s.add(Layout(blueprint_id=plan.id,geometry=Geometry(width_px=100,height_px=100).model_dump()))
        s.commit()
        project_id=project.id;plan_id=plan.id
    folder=tmp_path/plan_id
    folder.mkdir();(folder/'preview.png').write_bytes(b'data')
    sentinel=tmp_path/'keep.txt';sentinel.write_text('keep')
    response=main.delete_project(project_id)
    assert response['deleted'] is True
    assert not folder.exists()
    assert sentinel.read_text()=='keep'
    with Session(engine) as s:
        assert s.get(Project,project_id) is None
        assert s.get(Blueprint,plan_id) is None
        assert not list(s.exec(select(Layout).where(Layout.blueprint_id==plan_id)).all())

def test_overlapping_model_openings_can_be_reviewed_without_metric_verification(monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},
                         poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main,'engine',engine)
    with Session(engine) as session:
        project=Project(title='overlap');session.add(project);session.flush()
        blueprint=Blueprint(project_id=project.id,filename='test.png',
             local_path='',preview_path='',width=992,height=440)
        session.add(blueprint);session.flush()
        geometry=Geometry(width_px=992,height_px=440,walls=[
            Wall(id='model-7',start=Pt(x=100,y=100),end=Pt(x=600,y=100))],
            openings=[
                Opening(id='model-door-a',kind='door',wall_id='model-7',
                         offset_m=.65,width_m=.9,height_m=2.1,sill_m=0,inferred=True),
                Opening(id='model-door-b',kind='door',wall_id='model-7',
                         offset_m=1.05,width_m=.9,height_m=2.1,sill_m=0,inferred=True)])
        session.add(Layout(blueprint_id=blueprint.id,geometry=geometry.model_dump()))
        session.commit();bid=blueprint.id
    parsed=Geometry.model_validate(geometry.model_dump())
    from app.geometry import validate_geometry
    assert any('Overlapping openings' in message for message in validate_geometry(parsed))
    saved=main.save_layout(bid,main.SaveLayout(geometry=parsed,structure_reviewed=True))
    assert saved.geometry['structure_reviewed'] is True
    assert not saved.verified
    from fastapi import HTTPException
    try:main.save_layout(bid,main.SaveLayout(geometry=parsed,verified=True))
    except HTTPException as exc:
        assert exc.status_code==422
        assert any('Overlapping openings' in issue for issue in exc.detail['issues'])
    else:raise AssertionError('Metric verification must reject overlap')

def test_click_near_multiple_predicted_openings_does_not_create_third(monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},
                         poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main,'engine',engine)
    with Session(engine) as session:
        project=Project(title='overlap');session.add(project);session.flush()
        blueprint=Blueprint(project_id=project.id,filename='test.png',local_path='',
             preview_path='',width=992,height=440)
        session.add(blueprint);session.flush()
        geometry=Geometry(width_px=992,height_px=440,walls=[
            Wall(id='model-7',start=Pt(x=100,y=100),end=Pt(x=600,y=100))],
            openings=[
                Opening(id='a',kind='window',wall_id='model-7',offset_m=.65,
                        width_m=.9,height_m=1.2,sill_m=.9,inferred=True),
                Opening(id='b',kind='window',wall_id='model-7',offset_m=1.05,
                        width_m=.9,height_m=1.2,sill_m=.9,inferred=True)])
        session.add(Layout(blueprint_id=blueprint.id,geometry=geometry.model_dump()))
        session.commit();bid=blueprint.id
    result=main.propose_opening(bid,main.ProvisionalOpeningInput(kind='door',
                                           wall_id='model-7',fraction=.34))
    parsed=Geometry.model_validate(result.geometry)
    assert len(parsed.openings)==2
    assert any(opening.kind=='door' for opening in parsed.openings)
