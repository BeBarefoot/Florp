"""Evaluation records must be immutable after scoring and tied to one image."""
import hashlib
import pytest
import numpy as np
import cv2
from fastapi import HTTPException
from sqlmodel import SQLModel,Session,create_engine,select
from sqlalchemy.pool import StaticPool
from app import main
from app.models import Project,Blueprint,Layout,ExtractionEvaluation
from app.geometry import Geometry,Wall,Pt

@pytest.fixture
def evaluation_setup(tmp_path,monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main,'engine',engine)
    image=tmp_path/'plan.png'
    assert cv2.imwrite(str(image),np.full((200,400,3),255,dtype='uint8'))
    with Session(engine) as session:
        project=Project(title='Evaluation')
        session.add(project);session.flush()
        blueprint=Blueprint(project_id=project.id,filename='plan.png',
            local_path=str(image),preview_path=str(image),width=400,height=200)
        session.add(blueprint);session.flush()
        session.add(Layout(blueprint_id=blueprint.id,version=1,
                           geometry=Geometry(width_px=400,height_px=200).model_dump()))
        session.commit()
        bid=blueprint.id
    return engine,bid,image

def geometry(*ids):
    return Geometry(width_px=400,height_px=200,
        walls=[Wall(id=id,start=Pt(x=20,y=30+i*40),end=Pt(x=300,y=30+i*40))
               for i,id in enumerate(ids)])

def start(bid,image,g):
    return main.start_extraction_evaluation(bid,main.EvaluationStartBody(
        provider='florp-fusion',image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
        base_layout_version=1,geometry=g))

def test_evaluation_records_original_baseline_and_scores_human_reference(evaluation_setup):
    engine,bid,image=evaluation_setup
    first=start(bid,image,geometry('model-1'))
    assert first['status']=='baseline'
    pending=main.list_extraction_evaluations(bid)
    assert pending[0]['status']=='baseline'
    assert pending[0]['metrics'] is None
    with pytest.raises(HTTPException) as missing_consent:
        main.finish_extraction_evaluation(bid,first['id'],main.EvaluationFinishBody(
           geometry=geometry('human-1','human-2'),correction_seconds=120))
    assert missing_consent.value.status_code==422
    result=main.finish_extraction_evaluation(bid,first['id'],main.EvaluationFinishBody(
           geometry=geometry('human-1','human-2'),correction_seconds=180,
           human_reviewed=True,notes='Missing interior wall'))
    assert result['status']=='completed'
    assert result['metrics']['walls']['recall']==.5
    assert result['metrics']['walls']['precision']==1.
    rows=main.list_extraction_evaluations(bid)
    assert rows[0]['status']=='completed'
    assert rows[0]['correction_seconds']==180
    with Session(engine) as session:
        ev=session.get(ExtractionEvaluation,first['id'])
        assert len(ev.baseline['walls'])==1
        assert len(ev.reference['walls'])==2
        assert len(list(session.exec(select(Layout).where(Layout.blueprint_id==bid)).all()))==1
    with pytest.raises(HTTPException) as repeat:
        main.finish_extraction_evaluation(bid,first['id'],main.EvaluationFinishBody(
            geometry=geometry('human-1'),correction_seconds=1,human_reviewed=True))
    assert repeat.value.status_code==409

def test_stale_baseline_rejected(evaluation_setup):
    _,bid,image=evaluation_setup
    with pytest.raises(HTTPException) as err:
        main.start_extraction_evaluation(bid,main.EvaluationStartBody(
           provider='florp-fusion',image_sha256='0'*64,base_layout_version=1,
           geometry=geometry('model-1')))
    assert err.value.status_code==409
    with pytest.raises(HTTPException) as invalid:
        main.start_extraction_evaluation(bid,main.EvaluationStartBody(
           provider='florp-fusion',image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
           base_layout_version=1,geometry=Geometry(width_px=400,height_px=200)))
    assert invalid.value.status_code==422

def test_starter_outline_cannot_be_reference(evaluation_setup):
    _,bid,image=evaluation_setup
    current=start(bid,image,geometry('model-1'))
    from app.geometry import fallback_geometry
    with pytest.raises(HTTPException) as err:
        main.finish_extraction_evaluation(bid,current['id'],main.EvaluationFinishBody(
          geometry=fallback_geometry(400,200),correction_seconds=20,human_reviewed=True))
    assert err.value.status_code==422

def test_evaluation_export_has_source_bound_baseline_and_completed_truth(evaluation_setup):
    _,bid,image=evaluation_setup
    record=start(bid,image,geometry('model-1'))
    before=main.get_extraction_evaluation(bid,record['id'])
    assert before['schema_version']==1
    assert before['reference'] is None
    assert before['baseline']['provider']=='florp-fusion'
    main.finish_extraction_evaluation(bid,record['id'],main.EvaluationFinishBody(
        geometry=geometry('human-1','human-2'),
        correction_seconds=90,notes='one partition missed',
        human_reviewed=True))
    after=main.get_extraction_evaluation(bid,record['id'])
    assert len(after['reference']['walls'])==2
    assert after['metrics']['walls']['recall']==.5
    assert after['correction_seconds']==90
    with pytest.raises(HTTPException) as missing:
        main.get_extraction_evaluation(bid,'missing-record')
    assert missing.value.status_code==404
