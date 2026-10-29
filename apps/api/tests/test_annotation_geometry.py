from app.annotation_geometry import reconstruct

def mask(kind,x0,y0,x1,y1):return {'kind':kind,'polygon':[(x0,y0),(x1,y0),(x1,y1),(x0,y1)]}

def test_opening_evidence_bridges_host_without_filling_unclassified_gap():
    walls=[mask('wall',10,20,60,26),mask('wall',80,20,150,26)]
    raw=reconstruct(walls,200,100,50)
    assert len(raw['geometry']['walls'])==2
    result=reconstruct(walls+[mask('window',60,20,80,26)],200,100,50)
    assert len(result['geometry']['walls'])==1
    assert len(result['geometry']['openings'])==1
    assert abs(result['geometry']['openings'][0]['width_m']-.4)<.001

def test_unknown_scale_preserves_pixel_openings():
    result=reconstruct([mask('wall',10,20,150,26),mask('door',60,20,80,26)],200,100)
    assert result['pixel_openings'][0]['width_px']==20
    assert result['geometry']['openings']==[]
    assert result['geometry']['px_per_meter'] is None

def test_no_host_or_ambiguous_host_is_an_issue():
    result=reconstruct([mask('door',60,20,80,26)],200,100)
    assert result['issues'][0]['kind']=='opening_host'
    assert result['pixel_openings']==[]

def test_touching_wall_footprints_join_corner():
    result=reconstruct([mask('wall',10,20,100,26),mask('wall',94,26,100,80)],200,100,50)
    plan=result['canonical_plan']
    assert len(plan['nodes'])==3

def test_footprint_metrics_include_false_positives():
    from app.dataset_evaluation import footprint_metrics
    truth=[mask('wall',0,0,20,10)]
    pred=truth+[mask('wall',40,0,60,10)]
    score=footprint_metrics(truth,pred)['wall']
    assert score['precision']==.5
    assert score['recall']==1
    assert score['iou']==.5

def test_bent_footprint_does_not_become_diagonal_bounding_box():
    wall={'kind':'wall','polygon':[(10,10),(100,10),(100,20),(20,20),(20,90),(10,90)]}
    result=reconstruct([wall],150,120,50)
    assert result['geometry']['walls']
    assert all(abs(w['start']['x']-w['end']['x'])<1 or abs(w['start']['y']-w['end']['y'])<1 for w in result['geometry']['walls'])
