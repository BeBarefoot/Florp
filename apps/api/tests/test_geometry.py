from app.geometry import fallback_geometry, Geometry, validate_geometry

def test_fallback_is_explicitly_unverified():
    g=fallback_geometry(800,600)
    assert len(g.rooms)==1 and len(g.walls)==4
    assert any('not AI extraction' in w for w in g.warnings)
    assert validate_geometry(g)

def test_opening_requires_a_wall():
    g=fallback_geometry(800,600).model_dump()
    g['openings']=[{'id':'o1','kind':'window','wall_id':'nonexistent','offset_m':0,'width_m':1,'height_m':1}]
    try:Geometry.model_validate(g)
    except ValueError:pass
    else:raise AssertionError('Missing wall incorrectly accepted')
