from app.geometry import Geometry,Wall,Pt
from app.graph_reconstruction import propose_connected_geometry

def wall(i,a,b):
    return Wall(id=i,start=Pt(x=a[0],y=a[1]),end=Pt(x=b[0],y=b[1]))
def square(gap=0):
    return Geometry(width_px=500,height_px=500,walls=[
       wall("top",(100,100),(300,100)),
       wall("right",(300+gap,100+gap),(300,300)),
       wall("bottom",(300,300),(100,300)),
       wall("left",(100,300),(100,100))])

def test_closed_rectangle_proposes_single_unverified_room():
    source=square()
    before=source.model_dump()
    g=propose_connected_geometry(source)
    assert len(g.rooms)==1
    assert g.rooms[0].id=='auto-room-1'
    assert not g.structure_reviewed
    assert g.rooms[0].confidence==0
    assert source.model_dump()==before

def test_small_gap_gets_snapped_to_form_room():
    g=propose_connected_geometry(square(gap=4),tolerance_px=6)
    assert len(g.rooms)==1

def test_large_gap_does_not_invent_a_room():
    g=propose_connected_geometry(square(gap=22),tolerance_px=6)
    assert not g.rooms

def test_tjunction_splits_adjacent_rooms():
    source=square()
    source.walls.append(wall("partition",(200,100),(200,300)))
    g=propose_connected_geometry(source)
    assert len(g.rooms)==2

def test_open_lines_have_no_floors():
    source=Geometry(width_px=500,height_px=500,walls=[
       wall("one",(10,10),(100,10)),wall("two",(100,10),(100,100))])
    assert propose_connected_geometry(source).rooms==[]
