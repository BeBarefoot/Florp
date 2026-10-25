import pytest
from app.model_reconstruction import reconstruct
from app.pretrained_detector import DetectorResult, DetectionBox
from app.geometry import fallback_geometry

def detected(kind,x1,y1,x2,y2):
    return DetectionBox(category=kind,confidence=.9,x1=x1,y1=y1,x2=x2,y2=y2)

def test_model_replaces_starter_polygon_and_creates_wall_opening():
    result=DetectorResult(image_width=800,image_height=600,boxes=[
        detected('wall',100,100,600,110),
        detected('wall',100,110,112,500),
        detected('door',230,95,265,125)
    ])
    draft=reconstruct(result,fallback_geometry(800,600))
    assert draft.rooms==[]
    assert len(draft.walls)==2
    assert draft.walls[0].id.startswith('model-')
    assert len(draft.openings)==1
    assert draft.openings[0].wall_id==draft.walls[0].id
    assert draft.openings[0].inferred

def test_no_wall_boxes_does_not_invent_geometry():
    result=DetectorResult(image_width=800,image_height=600,boxes=[
        detected('wall',100,100,150,149)])
    with pytest.raises(ValueError):reconstruct(result,fallback_geometry(800,600))
