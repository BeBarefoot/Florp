import pytest
from pydantic import ValidationError
from app.geometry import Geometry, Room, Pt, Opening

def geometry():
    return Geometry(width_px=800,height_px=600,px_per_meter=100,rooms=[
        Room(id='r',points=[Pt(x=100,y=100),Pt(x=500,y=100),Pt(x=500,y=400),Pt(x=100,y=400)])
    ])

def test_boundary_window():
    g=geometry().model_dump()
    g['openings']=[dict(id='window',kind='window',wall_id='boundary:r:0',offset_m=1,width_m=1,height_m=1.2,sill_m=.9)]
    assert Geometry.model_validate(g).openings[0].wall_id=='boundary:r:0'

def test_opening_exceeds_wall_rejected():
    g=geometry().model_dump()
    g['openings']=[dict(id='window',kind='window',wall_id='boundary:r:0',offset_m=3.5,width_m=1,height_m=1,sill_m=.9)]
    with pytest.raises(ValidationError):Geometry.model_validate(g)

def test_overlapping_openings_rejected():
    g=geometry().model_dump()
    g['openings']=[dict(id=str(i),kind='door',wall_id='boundary:r:0',offset_m=x,width_m=1,height_m=2.1,sill_m=0) for i,x in enumerate([1,1.5])]
    with pytest.raises(ValidationError):Geometry.model_validate(g)

def test_missing_wall_rejected():
    g=geometry().model_dump()
    g['openings']=[dict(id='a',kind='door',wall_id='nonexistent',offset_m=0,width_m=.9,height_m=2,sill_m=0)]
    with pytest.raises(ValidationError):Geometry.model_validate(g)
