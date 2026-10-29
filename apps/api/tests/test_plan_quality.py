from app.geometry import Geometry,Wall,Pt,fallback_geometry
from app.plan_quality import assess_plan

def test_placeholder_is_not_a_room_or_structure():
    result=assess_plan(fallback_geometry(992,440))
    assert result['geometry']['walls']==[] and result['geometry']['rooms']==[]
    assert result['placeholder_wall_ids']==['w0','w1','w2','w3']
    assert not result['ready_for_metric_scene'] and not result['training_ground_truth']

def test_closed_unscaled_plan_still_not_ready_for_metric_scene():
    points=[(20,20),(180,20),(180,180),(20,180),(20,20)]
    g=Geometry(width_px=200,height_px=200,walls=[Wall(id=str(i),start=Pt(x=a[0],y=a[1]),end=Pt(x=b[0],y=b[1])) for i,(a,b) in enumerate(zip(points,points[1:]))])
    result=assess_plan(g,[{'candidate_id':'window-detection','decision':'window'}])
    assert result['topology']['faces']==1
    assert result['unresolved_opening_ids']==['window-detection']
    assert not result['ready_for_metric_scene']

def test_corrected_real_case_has_no_fake_room_after_normalization():
    import json
    from pathlib import Path
    doc=json.loads((Path(__file__).parent/'fixtures/reviewed_v4_geometry.json').read_text())
    g=Geometry.model_validate(doc['geometry']);before=g.model_dump()
    report=assess_plan(g)
    assert len(report['geometry']['walls'])==36
    assert report['geometry']['rooms']==[]
    assert report['geometry']['openings']==before['openings']
    assert report['structural_issues'] and report['metric_issues']
    assert not report['ready_for_metric_scene'] and g.model_dump()==before


def test_room_review_identifies_shared_partition_and_recomputes_on_removal():
    points=[((10,10),(190,10)),((190,10),(190,190)),((190,190),(10,190)),((10,190),(10,10)),((100,10),(100,190))]
    g=Geometry(width_px=200,height_px=200,walls=[Wall(id=str(i),start=Pt(x=a[0],y=a[1]),end=Pt(x=b[0],y=b[1])) for i,(a,b) in enumerate(points)])
    result=assess_plan(g)
    assert len(result['room_faces'])==2 and result['loose_endpoints']==[]
    assert all(r['shared_source_wall_ids']==['4'] and not r['verified'] for r in result['room_faces'])
    assert all(set(r['source_wall_ids'])<=set('01234') for r in result['room_faces'])
    merged=assess_plan(g.model_copy(update={'walls':g.walls[:4]}))
    assert len(merged['room_faces'])==1 and merged['room_faces'][0]['shared_source_wall_ids']==[]
    opened=assess_plan(g.model_copy(update={'walls':g.walls[:3]}))
    assert opened['room_faces']==[] and len(opened['loose_endpoints'])==2


def test_partly_exterior_source_wall_is_not_a_removable_shared_partition():
    # Vertical source extends beyond the two rooms; deleting it would remove exterior evidence.
    pts=[((10,10),(190,10)),((190,10),(190,180)),((190,180),(10,180)),((10,180),(10,10)),((100,0),(100,190))]
    g=Geometry(width_px=200,height_px=200,walls=[Wall(id=str(i),start=Pt(x=a[0],y=a[1]),end=Pt(x=b[0],y=b[1])) for i,(a,b) in enumerate(pts)])
    result=assess_plan(g)
    assert len(result['room_faces'])==2
    assert all('4' not in r['shared_source_wall_ids'] for r in result['room_faces'])
