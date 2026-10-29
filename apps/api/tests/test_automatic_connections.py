from PIL import Image,ImageDraw
from app.geometry import Geometry,Wall,Pt,Opening,Room
from app.automatic_connections import repair

def fixture(ink=True):
    g=Geometry(width_px=200,height_px=100,walls=[Wall(id='a',start=Pt(x=10,y=50),end=Pt(x=80,y=50)),Wall(id='b',start=Pt(x=83,y=50),end=Pt(x=160,y=50))])
    im=Image.new('L',(200,100),255)
    if ink:ImageDraw.Draw(im).line((10,50,160,50),fill=0,width=3)
    return g,im

def test_short_ink_supported_join_reduces_gaps_without_mutating_input():
    g,im=fixture();before=g.model_dump();out,changes,graph=repair(g,im,[])
    assert changes and graph.disconnected_components==1 and graph.dangling_nodes==2
    assert g.model_dump()==before and out.openings==g.openings

def test_blank_source_and_opening_evidence_are_not_bridged():
    g,im=fixture(False);assert repair(g,im,[])[1]==[]
    g,im=fixture();assert repair(g,im,[(76,45,90,55)])[1]==[]

def test_user_walls_and_hosted_openings_are_not_moved():
    g,im=fixture();g.walls[0].id='user-a';g.walls[1].id='user-b'
    assert repair(g,im,[])[1]==[]
    g,im=fixture();g.openings=[Opening(id='d',kind='door',wall_id='a',offset_m=0,width_m=.4,height_m=2)]
    out,changes,_=repair(g,im,[])
    assert out.walls[0]==g.walls[0] and out.openings==g.openings

def test_reviewed_rooms_and_dimension_mismatches_protected():
    import pytest
    g,im=fixture();g.structure_reviewed=True;assert repair(g,im,[])[1]==[]
    g.structure_reviewed=False;g.rooms=[Room(id='r',points=[Pt(x=1,y=1),Pt(x=20,y=1),Pt(x=20,y=20)])]
    assert repair(g,im,[])[1]==[]
    with pytest.raises(ValueError,match='dimensions'):repair(g,Image.new('L',(20,20)),[])
