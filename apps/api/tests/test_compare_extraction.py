"""Unified comparison is read-only and uses one canonical stored raster."""
import hashlib
from pathlib import Path
import cv2
import numpy as np
from sqlmodel import Session,SQLModel,create_engine,select
from sqlalchemy.pool import StaticPool
from app import main
from app.models import Project,Blueprint,Layout
from app.geometry import Geometry
from app.pretrained_detector import DetectorResult,DetectionBox

def test_compare_models_does_not_replace_saved_draft(tmp_path,monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},
                         poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main,'engine',engine)
    source=np.full((200,400,3),255,dtype='uint8')
    source[97:104,30:340]=0
    file=tmp_path/'preview.png'
    assert cv2.imwrite(str(file),source)
    original_bytes=file.read_bytes()
    with Session(engine) as s:
        project=Project(title='compare')
        s.add(project);s.flush()
        bp=Blueprint(project_id=project.id,filename='plan.png',
                     local_path=str(file),preview_path=str(file),
                     width=400,height=200)
        s.add(bp);s.flush()
        draft=Geometry(width_px=400,height_px=200)
        s.add(Layout(blueprint_id=bp.id,geometry=draft.model_dump()))
        s.commit();bid=bp.id
    calls=[]
    def fake_mask(path,width,height):
        calls.append(('mask',str(path),width,height))
        mask=np.zeros((200,400),dtype='uint8')
        mask[97:104,30:340]=255
        return mask,{'provider':'fixture-yytsi','checkpoint':'fixture.pt',
                     'wall_threshold':.46,'multiscale':{'tiles':3}}
    def fake_boxes(path,width,height):
        calls.append(('yolo',str(path),width,height))
        return DetectorResult(image_width=width,image_height=height,boxes=[
            DetectionBox(category='wall',confidence=.95,x1=30,y1=97,x2=340,y2=104)])
    monkeypatch.setattr(main,'predict_yytsi_raster',fake_mask)
    monkeypatch.setattr(main,'detect_objects',fake_boxes)
    monkeypatch.setattr(main.settings,'wall_segmentation_provider','yytsi')
    result=main.compare_extraction(bid)
    assert result['saved'] is False
    assert result['comparison']['fused_walls']>=1
    assert result['input_manifest']['source_preview_sha256']==hashlib.sha256(original_bytes).hexdigest()
    assert result['input_manifest']['same_original_preview_for_both_models'] is True
    assert calls==[('mask',str(file),400,200),('yolo',str(file),400,200)]
    with Session(engine) as s:
        rows=list(s.exec(select(Layout).where(Layout.blueprint_id==bid)).all())
        assert len(rows)==1
        assert rows[0].geometry==draft.model_dump()
    assert file.read_bytes()==original_bytes

def test_fusion_review_event_export_and_hash_guard(tmp_path,monkeypatch):
    from fastapi import HTTPException
    from app.models import FusionCandidateReview
    from app.evidence_fusion import FusedCandidate
    from app.geometry import Pt
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},
                         poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main,'engine',engine)
    preview=tmp_path/'plan.png'
    assert cv2.imwrite(str(preview),np.full((200,400,3),255,dtype='uint8'))
    with Session(engine) as session:
        p=Project(title='training');session.add(p);session.flush()
        bp=Blueprint(project_id=p.id,filename='plan.png',local_path=str(preview),
             preview_path=str(preview),width=400,height=200)
        session.add(bp);session.flush()
        session.add(Layout(blueprint_id=bp.id,
                           geometry=Geometry(width_px=400,height_px=200).model_dump()))
        session.commit();bid=bp.id
    candidate=FusedCandidate(id='yolo-only-4',start=Pt(x=10,y=20),end=Pt(x=200,y=20),
                             sources=['yolo_box:4'],mask_support=.0,
                             category='yolo_only',review_priority=.5)
    sha=hashlib.sha256(preview.read_bytes()).hexdigest()
    body=main.FusionReviewBody(preview_sha256=sha,candidate=candidate.model_dump(),
        decision='accept',input_manifest={'source_preview_sha256':sha,'segmentation_provider':'fixture-yytsi'})
    event=main.review_fusion_candidate(bid,body)
    assert event['saved'] is True
    assert event['decision']=='accept'
    exported=main.training_export(bid)
    assert exported['fusion_candidate_reviews'][0]['candidate_id']=='yolo-only-4'
    assert exported['fusion_candidate_reviews'][0]['preview_sha256']==sha
    assert exported['schema_version']==2
    assert exported['fusion_candidate_reviews'][0]['input_manifest']['segmentation_provider']=='fixture-yytsi'
    with Session(engine) as session:
        assert len(list(session.exec(select(Layout).where(Layout.blueprint_id==bid)).all()))==1
    try:
        main.review_fusion_candidate(bid,body.model_copy(update={'preview_sha256':'0'*64}))
    except HTTPException as err:assert err.status_code==409
    else:raise AssertionError('Stale image review must be rejected')

def test_fusion_candidate_can_be_reclassified_as_door_or_window(tmp_path,monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},
                         poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(main,'engine',engine)
    preview=tmp_path/'plan.png'
    assert cv2.imwrite(str(preview),np.full((200,400,3),255,dtype='uint8'))
    with Session(engine) as session:
        project=Project(title='opening labels')
        session.add(project);session.flush()
        bp=Blueprint(project_id=project.id,filename='plan.png',
                     local_path=str(preview),preview_path=str(preview),
                     width=400,height=200)
        session.add(bp);session.flush()
        session.add(Layout(blueprint_id=bp.id,
                           geometry=Geometry(width_px=400,height_px=200).model_dump()))
        session.commit();bid=bp.id
    from app.evidence_fusion import FusedCandidate
    from app.geometry import Pt
    candidate=FusedCandidate(id='yolo-wall-6',start=Pt(x=50,y=60),
            end=Pt(x=140,y=60),sources=['yolo_box:6'],
            mask_support=.1,category='yolo_only')
    hash_value=hashlib.sha256(preview.read_bytes()).hexdigest()
    for classification in ('door','window'):
        response=main.review_fusion_candidate(bid,main.FusionReviewBody(
            preview_sha256=hash_value,candidate=candidate.model_dump(),
            decision=classification))
        assert response['decision']==classification
    export=main.training_export(bid)
    assert [e['decision'] for e in export['fusion_candidate_reviews']]==['door','window']
    with Session(engine) as session:
        stored=list(session.exec(select(Layout).where(Layout.blueprint_id==bid)).all())
        assert len(stored)==1
        assert stored[0].geometry['openings']==[]

import pytest

def test_merge_reviewed_walls_after_layout_version_advances(tmp_path,monkeypatch):
    from app.evidence_fusion import FusedCandidate
    from app.geometry import Wall,Pt
    from app.models import FusionCandidateReview
    from fastapi import HTTPException
    db=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    SQLModel.metadata.create_all(db)
    monkeypatch.setattr(main,'engine',db)
    image=tmp_path/'plan.png'
    assert cv2.imwrite(str(image),np.full((200,400,3),255,dtype='uint8'))
    digest=hashlib.sha256(image.read_bytes()).hexdigest()
    preserved=Wall(id='user-wall',start=Pt(x=30,y=20),end=Pt(x=30,y=150))
    original=Geometry(width_px=400,height_px=200,walls=[preserved])
    candidate=FusedCandidate(id='mask-gap',start=Pt(x=30,y=100),end=Pt(x=250,y=100),
        category='yytsi_only',sources=['yytsi_mask'],mask_support=1)
    with Session(db) as session:
        project=Project(title='test');session.add(project);session.flush()
        blueprint=Blueprint(project_id=project.id,filename='plan.png',
            local_path=str(image),preview_path=str(image),width=400,height=200)
        session.add(blueprint);session.flush()
        session.add(Layout(blueprint_id=blueprint.id,version=6,geometry=original.model_dump()))
        session.add(FusionCandidateReview(blueprint_id=blueprint.id,
            preview_sha256=digest,candidate_id=candidate.id,category='yytsi_only',
            decision='accept',candidate=candidate.model_dump()))
        session.commit()
        bid=blueprint.id
    body=main.MergeFusionDraftBody(preview_sha256=digest,layout_version=6,
        geometry=original,candidate_ids=[candidate.id])
    merged=main.merge_reviewed_fusion_walls(bid,body)
    assert (merged['added'],merged['already_present'],merged['ignored'])==(1,0,0)
    assert [w['id'] for w in merged['geometry']['walls']]==['user-wall','mask-gap']
    assert original.walls==[preserved]
    with Session(db) as session:
        rows=list(session.exec(select(Layout).where(Layout.blueprint_id==bid)).all())
        assert len(rows)==1 and rows[0].version==6
        assert rows[0].geometry==original.model_dump()
        session.add(Layout(blueprint_id=bid,version=7,geometry=merged['geometry']))
        session.commit()
    newer=main.merge_reviewed_fusion_walls(bid,main.MergeFusionDraftBody(
        preview_sha256=digest,layout_version=7,
        geometry=Geometry.model_validate(merged['geometry']),
        candidate_ids=[candidate.id]))
    assert (newer['added'],newer['already_present'])==(0,1)
    with pytest.raises(HTTPException) as error:
        main.merge_reviewed_fusion_walls(bid,body)
    assert error.value.status_code==409

def test_reviewed_geometry_export_is_source_bound_and_not_marked_ground_truth(tmp_path,monkeypatch):
    from app.models import FusionCandidateReview
    from app.geometry import Pt,Wall
    from app.evidence_fusion import FusedCandidate
    db=create_engine('sqlite://',connect_args={'check_same_thread':False},
                     poolclass=StaticPool)
    SQLModel.metadata.create_all(db)
    monkeypatch.setattr(main,'engine',db)
    path=tmp_path/'preview.png'
    assert cv2.imwrite(str(path),np.full((200,400,3),255,dtype='uint8'))
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    draft=Geometry(width_px=400,height_px=200,walls=[
        Wall(id='approved',start=Pt(x=10,y=20),end=Pt(x=180,y=20))])
    candidate=FusedCandidate(id='approved',start=Pt(x=10,y=20),
        end=Pt(x=180,y=20),sources=['yytsi_mask'],mask_support=.95,
        category='yytsi_only')
    with Session(db) as session:
        project=Project(title='reviewed');session.add(project);session.flush()
        bp=Blueprint(project_id=project.id,filename='plan.png',
            local_path=str(path),preview_path=str(path),
            width=400,height=200)
        session.add(bp);session.flush()
        session.add(Layout(blueprint_id=bp.id,version=3,geometry=draft.model_dump()))
        session.add(FusionCandidateReview(blueprint_id=bp.id,
            preview_sha256=digest,candidate_id='approved',
            category='yytsi_only',decision='accept',candidate=candidate.model_dump()))
        session.commit();bid=bp.id
    result=main.reviewed_geometry_export(bid)
    assert result['schema_version']==1
    assert result['source_preview_sha256']==digest
    assert result['layout_version']==3
    assert result['geometry']==draft.model_dump()
    assert len(result['review_labels'])==1
    assert result['review_labels'][0]['decision']=='accept'
    assert result['ground_truth_status']=='not independently validated'
