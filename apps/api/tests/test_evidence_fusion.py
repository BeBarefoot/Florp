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
    assert 'yolo_box:0' in candidates[0].sources
    assert summary.accepted_yolo_candidates==1
    assert original.walls==[]
    assert proposal.structure_reviewed is False

def test_yolo_box_without_mask_support_not_silently_added():
    mask=np.zeros((200,400),dtype='uint8')
    mask[97:104,30:340]=255
    report=WallMaskReport(coverage_fraction=.03,line_count=1,
        lines=[line(30,100,340,100)])
    _,items,summary=fuse_evidence(base(),mask,report,yolo(wall(30,40,340,47)))
    assert len(items)==1
    assert summary.rejected_yolo_candidates==1

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
