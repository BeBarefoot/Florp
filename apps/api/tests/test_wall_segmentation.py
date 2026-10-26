import numpy as np
import pytest
from app.wall_segmentation import mask_centerlines, propose_mask_walls
from app.geometry import Geometry, Wall, Pt

def test_empty_wall_mask_does_not_invent_geometry():
    report=mask_centerlines(np.zeros((180,320),dtype=np.uint8))
    assert report.line_count==0
    assert report.coverage_fraction==0

def test_thick_horizontal_wall_mask_produces_supported_lines():
    mask=np.zeros((180,320),dtype=np.uint8)
    mask[70:84,20:280]=255
    report=mask_centerlines(mask,min_length=60)
    assert report.coverage_fraction>0
    assert report.line_count>0
    assert all(abs(line.y2-line.y1)<=max(1,abs(line.x2-line.x1)*.16) for line in report.lines)

def test_furniture_like_full_mask_is_rejected():
    mask=np.ones((100,100),dtype=np.uint8)*255
    with pytest.raises(ValueError,match='covers most'):
        mask_centerlines(mask)

def test_mask_proposal_does_not_preserve_incorrect_old_wall_ids():
    from app.wall_segmentation import WallMaskReport, MaskLine
    original=Geometry(width_px=320,height_px=180,walls=[
        Wall(id='model-8',start=Pt(x=5,y=5),end=Pt(x=40,y=5))])
    report=WallMaskReport(coverage_fraction=.01,line_count=1,lines=[
        MaskLine(x1=20,y1=70,x2=280,y2=70,support=1.)])
    draft=propose_mask_walls(original,report)
    assert [wall.id for wall in draft.walls]==['mask-0']
    assert original.walls[0].id=='model-8'
    assert draft.structure_reviewed is False

def test_mask_run_recovers_interior_wall_when_hough_returns_none(monkeypatch):
    from app import wall_segmentation
    monkeypatch.setattr(wall_segmentation.cv2,'HoughLinesP',lambda *args,**kwargs:None)
    mask=np.zeros((160,320),dtype=np.uint8)
    mask[30:33,50:260]=255  # three-pixel wall, missed by Hough
    result=mask_centerlines(mask,min_length=50)
    assert any(abs(line.y2-line.y1)<=1 and abs(line.x2-line.x1)>=190
               for line in result.lines)
    assert result.coverage_fraction>0

def test_unsupported_short_mask_does_not_invent_wall(monkeypatch):
    from app import wall_segmentation
    monkeypatch.setattr(wall_segmentation.cv2,'HoughLinesP',lambda *args,**kwargs:None)
    mask=np.zeros((160,320),dtype=np.uint8)
    mask[40:43,50:67]=255
    result=mask_centerlines(mask,min_length=50)
    assert result.line_count==0
