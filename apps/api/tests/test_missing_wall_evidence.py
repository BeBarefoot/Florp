import cv2
import numpy as np
from app.geometry import Geometry, Wall, Pt
from app.missing_wall_evidence import gap_suggestions

def wall(name,a,b):
    return Wall(id=name,start=Pt(x=a[0],y=a[1]),end=Pt(x=b[0],y=b[1]))

def test_supported_missing_gap_suggested_without_modifying_walls(tmp_path):
    image=np.full((200,400),255,dtype=np.uint8)
    cv2.line(image,(120,90),(220,90),0,3)
    preview=tmp_path/'preview.png';cv2.imwrite(str(preview),image)
    geometry=Geometry(width_px=400,height_px=200,walls=[
        wall('a',(40,90),(120,90)),wall('b',(220,90),(330,90))])
    before=geometry.model_dump()
    proposals=gap_suggestions(geometry,preview,max_gap_px=150)
    assert any(abs(p.start.x-120)<1 and abs(p.end.x-220)<1 and p.image_support>.64
               for p in proposals)
    assert geometry.model_dump()==before

def test_blank_gap_never_invented(tmp_path):
    image=np.full((200,400),255,dtype=np.uint8)
    preview=tmp_path/'preview.png';cv2.imwrite(str(preview),image)
    geometry=Geometry(width_px=400,height_px=200,walls=[
        wall('a',(40,90),(120,90)),wall('b',(220,90),(330,90))])
    assert gap_suggestions(geometry,preview,max_gap_px=150)==[]

def test_distant_unaligned_ends_not_connected(tmp_path):
    image=np.zeros((200,400),dtype=np.uint8)
    preview=tmp_path/'preview.png';cv2.imwrite(str(preview),image)
    geometry=Geometry(width_px=400,height_px=200,walls=[
        wall('a',(40,90),(120,90)),wall('b',(220,125),(330,125))])
    assert gap_suggestions(geometry,preview,max_gap_px=150)==[]
