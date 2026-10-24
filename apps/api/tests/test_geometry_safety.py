from app.geometry import fallback_geometry, validate_geometry, Pt, Wall

def test_bowtie_room_not_verifiable():
    g=fallback_geometry(800,600)
    g.px_per_meter=60
    g.rooms[0].points=[Pt(x=100,y=100),Pt(x=400,y=400),Pt(x=100,y=400),Pt(x=400,y=100)]
    assert any('self-intersects' in x for x in validate_geometry(g))

def test_invalid_wall_is_rejected_by_validation():
    g=fallback_geometry(800,600)
    g.px_per_meter=60
    g.walls.append(Wall(id='manual',start=Pt(x=100,y=100),end=Pt(x=101,y=100)))
    assert any('too short' in x for x in validate_geometry(g))
