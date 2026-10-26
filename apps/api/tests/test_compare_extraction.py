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
    body=main.FusionReviewBody(preview_sha256=sha,candidate=candidate.model_dump(),decision='accept')
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
