import cv2
import numpy as np
from app.exterior_recovery import suggest_bottom_runs
from app.geometry import Geometry,Wall,Pt

def wall(name,a,b):
    return Wall(id=name,start=Pt(x=a[0],y=a[1]),end=Pt(x=b[0],y=b[1]))

def test_dark_lower_boundary_attached_to_vertical_wall_proposed(tmp_path):
    image=np.full((220,500),245,dtype=np.uint8)
    cv2.line(image,(80,194),(430,194),20,4)
    path=tmp_path/'preview.png';cv2.imwrite(str(path),image)
    g=Geometry(width_px=500,height_px=220,walls=[
        wall('right',(430,55),(430,194)),wall('left',(80,60),(80,145))])
    original=g.model_dump()
    candidates=suggest_bottom_runs(g,path,min_length_fraction=.25)
    assert candidates, 'Source-supported bottom wall should be a review proposal'
    assert candidates[0].axis=='horizontal'
    assert candidates[0].image_support>.8
    assert candidates[0].end.x-candidates[0].start.x>250
    assert g.model_dump()==original

def test_blank_lower_area_does_not_fabricate_wall(tmp_path):
    image=np.full((220,500),255,dtype=np.uint8)
    path=tmp_path/'preview.png';cv2.imwrite(str(path),image)
    g=Geometry(width_px=500,height_px=220,walls=[
        wall('right',(430,55),(430,194)),wall('left',(80,60),(80,145))])
    assert suggest_bottom_runs(g,path,min_length_fraction=.25)==[]

def test_no_vertical_structural_anchor_means_no_bottom_proposal(tmp_path):
    image=np.full((220,500),255,dtype=np.uint8)
    cv2.line(image,(80,194),(430,194),0,4)
    path=tmp_path/'preview.png';cv2.imwrite(str(path),image)
    g=Geometry(width_px=500,height_px=220,walls=[
        wall('top',(80,45),(430,45))])
    assert suggest_bottom_runs(g,path,min_length_fraction=.25)==[]
