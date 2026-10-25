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
    assert draft.openings[0].source_detection_id=='model-box-2'
    assert draft.openings[0].reviewed is False

def test_no_wall_boxes_does_not_invent_geometry():
    result=DetectorResult(image_width=800,image_height=600,boxes=[
        detected('wall',100,100,150,149)])
    with pytest.raises(ValueError):reconstruct(result,fallback_geometry(800,600))

def test_filter_audit_counts_short_and_nonelongated_boxes():
    from app.model_reconstruction import detection_audit
    boxes=[
        DetectionBox(category='wall',confidence=.9,x1=10,y1=10,x2=200,y2=20),
        DetectionBox(category='wall',confidence=.9,x1=10,y1=10,x2=25,y2=20),
        DetectionBox(category='wall',confidence=.9,x1=50,y1=50,x2=100,y2=94),
        DetectionBox(category='window',confidence=.9,x1=100,y1=100,x2=140,y2=120),
    ]
    data=detection_audit(DetectorResult(image_width=800,image_height=600,boxes=boxes))
    assert data['wall_boxes']==3
    assert data['accepted_wall_boxes']==1
    assert data['too_short']==1
    assert data['not_elongated']==1
    assert data['window_boxes']==1

def test_reviewed_opening_roundtrips_without_changing_structural_walls():
    from app.geometry import Geometry
    result=DetectorResult(image_width=800,image_height=600,boxes=[
        detected('wall',100,100,600,110),detected('door',230,95,265,125)])
    draft=reconstruct(result,fallback_geometry(800,600))
    before=[w.model_dump() for w in draft.walls]
    draft.openings[0].reviewed=True
    reread=Geometry.model_validate_json(draft.model_dump_json())
    assert reread.openings[0].reviewed is True
    assert reread.openings[0].source_detection_id=='model-box-1'
    assert [w.model_dump() for w in reread.walls]==before
