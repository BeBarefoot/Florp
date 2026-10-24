from app.evidence import Evidence, Segment
from app.geometry import fallback_geometry, Wall, Pt
from app.reconcile import reconcile

def test_preserve_geometry_on_unrelated_lines():
    g=fallback_geometry(800,600)
    g.px_per_meter=60
    coords=g.rooms[0].model_dump()
    ev=Evidence(width=800,height=600,segments=[Segment(x1=10,y1=10,x2=100,y2=10,source='raster_hough',confidence=.5)])
    out=reconcile(g,ev)
    assert out.rooms[0].model_dump()==coords
    assert len(out.warnings)>0

def test_duplicate_wall_not_kept():
    g=fallback_geometry(800,600)
    g.walls.append(Wall(id='duplicate',start=g.walls[0].start,end=g.walls[0].end))
    out=reconcile(g,Evidence(width=800,height=600))
    assert len(out.walls)==4

def test_opening_wall_reference_preserved():
    g=fallback_geometry(800,600)
    from app.geometry import Opening
    g.walls.append(Wall(id='duplicate',start=g.walls[0].start,end=g.walls[0].end))
    g.openings.append(Opening(id='win',kind='window',wall_id='duplicate',offset_m=0,width_m=.5,height_m=1))
    out=reconcile(g,Evidence(width=800,height=600))
    assert any(w.id=='duplicate' for w in out.walls)
