import numpy as np
import pytest
from app.evidence_fusion import fuse_evidence
from app.geometry import Geometry,Pt
from app.wall_segmentation import WallMaskReport,MaskLine
from app.pretrained_detector import DetectorResult,DetectionBox

def base():
    return Geometry(width_px=400,height_px=200)
def line(x1,y1,x2,y2):
    return MaskLine(x1=x1,y1=y1,x2=x2,y2=y2,support=.95)
def yolo(*boxes):
    return DetectorResult(image_width=400,image_height=200,boxes=list(boxes))
def wall(x1,y1,x2,y2):
    return DetectionBox(category='wall',confidence=.95,x1=x1,y1=y1,x2=x2,y2=y2)

def test_same_wall_supported_by_yolo_is_not_duplicated():
    mask=np.zeros((200,400),dtype='uint8')
    mask[97:104,30:340]=255
    report=WallMaskReport(coverage_fraction=.03,line_count=1,
        lines=[line(30,100,340,100)])
    original=base()
    proposal,candidates,summary=fuse_evidence(original,mask,report,yolo(wall(30,97,340,104)))
    assert len(candidates)==1
    assert 'yytsi_mask' in candidates[0].sources
    assert candidates[0].id=='yolo-wall-0'
    assert 'yolo_box:0' in candidates[0].sources
    assert summary.accepted_yolo_candidates==1
    assert original.walls==[]
    assert proposal.structure_reviewed is False

def test_yolo_box_without_mask_support_remains_reviewable_not_auto_added():
    mask=np.zeros((200,400),dtype='uint8')
    mask[97:104,30:340]=255
    report=WallMaskReport(coverage_fraction=.03,line_count=1,
        lines=[line(30,100,340,100)])
    proposed,items,summary=fuse_evidence(base(),mask,report,yolo(wall(30,40,340,47)))
    assert len(items)==2
    assert summary.rejected_yolo_candidates==1
    assert summary.yolo_only_candidates==1
    assert any(item.category=='yolo_only' for item in items)
    assert len(proposed.walls)==1  # YOLO-only primary; mask-only remains optional review

def test_mismatched_model_dimensions_refuse_fusion():
    incorrect=DetectorResult(image_width=399,image_height=200,boxes=[])
    with pytest.raises(ValueError,match='coordinates differ'):
        fuse_evidence(base(),np.zeros((200,400),dtype='uint8'),
             WallMaskReport(coverage_fraction=0,line_count=0,lines=[]),incorrect)

def test_mask_only_fallback_and_topology_proposal():
    mask=np.zeros((200,400),dtype='uint8')
    mask[90:96,20:300]=255
    report=WallMaskReport(coverage_fraction=.02,line_count=1,
         lines=[line(20,93,300,93)])
    proposal,items,summary=fuse_evidence(base(),mask,report,None)
    assert len(items)==1
    assert len(proposal.walls)==1
    assert summary.yolo_wall_boxes==0
    assert summary.topology['wall_count']==1

def test_yolo_only_does_not_depend_on_mask_for_review():
    mask=np.zeros((200,400),dtype='uint8')
    report=WallMaskReport(coverage_fraction=0,line_count=0,lines=[])
    proposal,candidates,summary=fuse_evidence(base(),mask,report,
         yolo(wall(35,40,320,47)))
    assert summary.yolo_only_candidates==1
    assert summary.yytsi_only_candidates==0
    assert candidates[0].category=='yolo_only'
    assert candidates[0].yolo_confidence==.95
    assert len(proposal.walls)==1

def test_agreement_has_higher_priority_than_isolated_yolo():
    mask=np.zeros((200,400),dtype='uint8')
    mask[90:96,20:300]=255
    report=WallMaskReport(coverage_fraction=.02,line_count=1,
         lines=[line(20,93,300,93)])
    proposal,candidates,summary=fuse_evidence(base(),mask,report,
         yolo(wall(20,90,300,96),wall(30,40,310,46)))
    assert summary.agreed_candidates==1
    assert summary.yolo_only_candidates==1
    assert candidates[0].category=='agreed'
    assert candidates[0].review_priority>candidates[1].review_priority
    assert len(proposal.walls)==2  # Both distinct YOLO wall axes remain in preview

def test_two_predictions_of_same_wall_are_one_review_item():
    mask=np.zeros((200,400),dtype='uint8')
    mask[97:103,30:340]=255
    report=WallMaskReport(coverage_fraction=.02,line_count=2,
         lines=[line(30,100,340,100),line(36,103,330,103)])
    proposal,items,_=fuse_evidence(base(),mask,report,
         yolo(wall(30,97,340,103)))
    assert len(items)==1
    assert items[0].id=='yolo-wall-0'
    assert len(proposal.walls)==1

def test_duplicate_yolo_boxes_do_not_require_double_review():
    mask=np.zeros((200,400),dtype='uint8')
    report=WallMaskReport(coverage_fraction=0,line_count=0,lines=[])
    proposal,candidates,summary=fuse_evidence(base(),mask,report,
        yolo(wall(20,90,310,96),wall(35,91,300,97)))
    assert len(candidates)==1
    assert len(proposal.walls)==1
    assert len([s for s in candidates[0].sources if s.startswith('yolo_box:')])==2

def test_yolo_available_with_no_wall_boxes_does_not_silently_promote_mask_only():
    mask=np.zeros((200,400),dtype='uint8')
    mask[90:96,20:300]=255
    report=WallMaskReport(coverage_fraction=.02,line_count=1,
         lines=[line(20,93,300,93)])
    proposed,items,summary=fuse_evidence(base(),mask,report,yolo())
    assert len(items)==1
    assert items[0].category=='yytsi_only'
    assert proposed.walls==[]
    assert summary.yytsi_only_candidates==1
