from app.geometry import Geometry,Wall,Pt,Opening
from app.connectivity_preview import preview_connectivity
import pytest

def wall(id,a,b):
    return Wall(id=id,start=Pt(x=a[0],y=a[1]),end=Pt(x=b[0],y=b[1]))

def test_t_junction_moves_only_loose_endpoint_without_changing_saved_input():
    g=Geometry(width_px=300,height_px=200,walls=[
        wall('horizontal',(20,100),(220,100)),
        wall('vertical',(120,50),(120,96)),
    ])
    original=g.model_dump()
    result=preview_connectivity(g)
    assert result.geometry.walls[1].end==Pt(x=120,y=100)
    assert result.geometry.walls[0]==g.walls[0]
    assert result.geometry.structure_reviewed is False
    assert len(result.changes)==1
    assert result.changes[0].reason=='perpendicular T junction'
    assert g.model_dump()==original
    assert result.after_dangling<=result.before_dangling

def test_endpoint_join_keeps_line_axis():
    g=Geometry(width_px=300,height_px=200,walls=[
        wall('a',(10,80),(100,80)),
        wall('b',(104,80),(210,80))])
    result=preview_connectivity(g)
    assert all(w.start.y==80 and w.end.y==80 for w in result.geometry.walls)
    assert any(c.distance_px<=5 for c in result.changes)
    assert g.walls[1].start.x==104

def test_does_not_bridge_large_missing_partition_or_parallel_wall_thickness():
    g=Geometry(width_px=300,height_px=200,walls=[
        wall('a',(10,50),(95,50)),
        wall('b',(120,50),(210,50)),
        wall('parallel',(10,56),(95,56))])
    result=preview_connectivity(g)
    assert result.changes==[]

def test_doors_windows_are_never_shifted_or_dropped():
    g=Geometry(width_px=300,height_px=200,px_per_meter=50,
        walls=[wall('host',(20,100),(220,100)),
               wall('t',(120,50),(120,97))],
        openings=[Opening(id='door',kind='door',wall_id='t',offset_m=0,
                          width_m=.4,height_m=2.1)])
    result=preview_connectivity(g)
    assert result.geometry.walls[1]==g.walls[1]
    assert result.geometry.openings==g.openings

def test_pure_read_only_preview_has_no_metric_or_room_changes():
    from app.geometry import Room
    g=Geometry(width_px=300,height_px=200,rooms=[
        Room(id='verified',points=[Pt(x=20,y=20),Pt(x=250,y=20),Pt(x=250,y=170)]),
    ],walls=[wall('a',(10,80),(100,80)),wall('b',(104,80),(210,80))])
    r=preview_connectivity(g)
    assert r.geometry.rooms==g.rooms
    assert r.geometry.px_per_meter is None
    assert all(w.id in ('a','b') for w in r.geometry.walls)

def test_tolerance_is_bounded():
    with pytest.raises(ValueError):
        preview_connectivity(Geometry(width_px=100,height_px=100),20)
