from app.geometry import Geometry,Wall,Pt
from app.opening_review import OpeningHint,associate_opening,create_opening

def geometry():
    return Geometry(width_px=500,height_px=250,walls=[
        Wall(id='w',start=Pt(x=30,y=90),end=Pt(x=400,y=90))])

def hint(id='window-a',kind='window',x1=170,y1=84,x2=230,y2=98):
    return OpeningHint(candidate_id=id,kind=kind,x1=x1,y1=y1,x2=x2,y2=y2,
        source_confidence=.9,reason='detected')

def test_detected_window_attaches_to_wall_and_keeps_original_unchanged():
    original=geometry()
    associated=associate_opening(original,hint())
    assert associated.wall_id=='w'
    result,status=create_opening(original,associated)
    assert status=='added'
    assert result.openings[0].kind=='window'
    assert result.openings[0].source_detection_id=='window-a'
    assert result.openings[0].inferred
    assert not result.openings[0].reviewed
    assert original.openings==[]

def test_same_detection_is_idempotent_and_updates_classification():
    associated=associate_opening(geometry(),hint())
    first,_=create_opening(geometry(),associated)
    revised=associated.model_copy(update={'kind':'door'})
    second,status=create_opening(first,revised)
    assert status=='updated'
    assert len(second.openings)==1
    assert second.openings[0].kind=='door'
    assert second.openings[0].sill_m==0

def test_overlapping_detection_not_added_twice():
    first,_=create_opening(geometry(),associate_opening(geometry(),hint()))
    second,status=create_opening(first,associate_opening(first,hint('another')))
    assert status=='overlap'
    assert len(second.openings)==1

def test_unattached_detection_remains_label_only():
    original=geometry()
    unrelated=hint(x1=170,y1=180,x2=230,y2=195)
    h=associate_opening(original,unrelated)
    assert h.wall_id is None
    result,status=create_opening(original,h)
    assert status=='unresolved'
    assert result.openings==[]

def test_ambiguous_two_walls_requires_manual_placement():
    g=geometry()
    g.walls.append(Wall(id='parallel',start=Pt(x=30,y=98),end=Pt(x=400,y=98)))
    resolved=associate_opening(g,hint(x1=160,y1=88,x2=230,y2=100))
    assert resolved.wall_id is None
    assert 'Two nearby walls' in resolved.reason
