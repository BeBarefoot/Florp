from app.geometry import Geometry, Wall, Pt
from app.topology import audit_topology

def w(name,a,b):
    return Wall(id=name,start=Pt(x=a[0],y=a[1]),end=Pt(x=b[0],y=b[1]))

def test_snapped_endpoint_component():
    g=Geometry(width_px=300,height_px=300,walls=[
        w("a",(20,20),(100,20)),w("b",(104,23),(104,150))])
    original=g.model_dump()
    result=audit_topology(g)
    assert result.disconnected_components==1
    assert result.junction_count==1
    assert g.model_dump()==original

def test_crossing_is_not_automatically_fused():
    g=Geometry(width_px=300,height_px=300,walls=[
        w("a",(20,100),(200,100)),w("b",(100,20),(100,200))])
    result=audit_topology(g)
    assert result.disconnected_components==2
    assert result.crossing_pairs==[("a","b")]

def test_no_walls_is_valid_audit():
    result=audit_topology(Geometry(width_px=200,height_px=100))
    assert result.wall_count==0
    assert result.disconnected_components==0
