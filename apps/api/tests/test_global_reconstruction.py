from copy import deepcopy
from PIL import Image, ImageDraw
import pytest
from app.geometry import Geometry, Wall, Opening, Pt
from app.graph_adapter import from_geometry, to_geometry
from app.global_reconstruction import propose_reconstruction, apply_candidates, topology


def broken_loop():
    points=[((20,20),(80,20)),((120,20),(180,20)),((180,20),(180,180)),
            ((180,180),(20,180)),((20,180),(20,20))]
    g=Geometry(width_px=200,height_px=200,px_per_meter=20,scale_source='user_confirmed',
        walls=[Wall(id=str(i),start=Pt(x=a[0],y=a[1]),end=Pt(x=b[0],y=b[1])) for i,(a,b) in enumerate(points)],
        openings=[Opening(id='window',kind='window',wall_id='2',offset_m=2,width_m=1,height_m=1,sill_m=1)])
    return from_geometry(g)


def raster(lines):
    image=Image.new('L',(200,200),255)
    draw=ImageDraw.Draw(image)
    for line in lines:draw.line(line,fill=0,width=3)
    return image


def test_supported_loop_closure_is_deterministic_and_lossless():
    plan=broken_loop();original=deepcopy(plan.model_dump())
    image=raster([[(80,20),(120,20)]])
    result=propose_reconstruction(plan,image)
    assert result==propose_reconstruction(plan,image)
    assert plan.model_dump()==original
    assert len(result['candidates'])==1
    assert result['before']['dangling']==2 and result['after']['dangling']==0
    assert result['after']['faces']==1
    proposal=apply_candidates(plan,result['candidates'])
    assert proposal.nodes==plan.nodes
    assert proposal.walls[:len(plan.walls)]==plan.walls
    assert proposal.openings==plan.openings
    assert all(not r.verified for r in proposal.rooms)
    assert proposal.walls[-1].inferred and proposal.walls[-1].evidence_ids
    assert to_geometry(proposal).openings==to_geometry(plan).openings
    assert to_geometry(proposal).rooms==[]


def test_blank_and_end_caps_cannot_justify_missing_wall():
    for image in [raster([]),raster([[(70,20),(81,20)],[(119,20),(130,20)]])]:
        result=propose_reconstruction(broken_loop(),image)
        assert result['candidates']==[]
        assert result['rejected']['insufficient_raster_support']==1
        assert result['before']==result['after']


def test_crossing_gap_is_rejected():
    plan=broken_loop()
    from app.graph_operations import apply_operation, GraphOperation
    plan=apply_operation(plan,GraphOperation(kind='add_wall',start=Pt(x=100,y=5),end=Pt(x=100,y=40)))
    result=propose_reconstruction(plan,raster([[(80,20),(120,20)]]))
    assert not result['candidates']
    assert result['rejected']['structural_conflict']==1


def test_supported_perpendicular_corner():
    g=Geometry(width_px=200,height_px=200,walls=[
        Wall(id='a',start=Pt(x=20,y=20),end=Pt(x=70,y=20)),
        Wall(id='b',start=Pt(x=100,y=50),end=Pt(x=100,y=100))])
    p=from_geometry(g)
    result=propose_reconstruction(p,raster([[(70,20),(100,20),(100,50)]]))
    assert len(result['candidates'])==1
    assert result['candidates'][0]['kind']=='corner'
    applied=apply_candidates(p,result['candidates'])
    assert len(applied.nodes)==len(p.nodes)+1
    assert topology(applied)['components']==1
    assert applied==apply_candidates(p,result['candidates'])


def test_limits_and_image_binding():
    plan=broken_loop()
    assert not propose_reconstruction(plan,raster([[(80,20),(120,20)]]),max_gap_px=30)['candidates']
    for kwargs in [{'max_gap_px':201},{'max_gap_px':float('nan')},{'min_support':.1}]:
        with pytest.raises(ValueError):propose_reconstruction(plan,raster([]),**kwargs)
    with pytest.raises(ValueError,match='dimensions'):
        propose_reconstruction(plan,Image.new('L',(100,100)))


def test_compatible_set_rejects_crossing_candidates():
    # Two individually valid repairs cross in the empty middle of four walls.
    g=Geometry(width_px=200,height_px=200,walls=[
        Wall(id='l',start=Pt(x=10,y=100),end=Pt(x=70,y=100)),
        Wall(id='r',start=Pt(x=130,y=100),end=Pt(x=190,y=100)),
        Wall(id='t',start=Pt(x=100,y=10),end=Pt(x=100,y=70)),
        Wall(id='b',start=Pt(x=100,y=130),end=Pt(x=100,y=190))])
    p=from_geometry(g)
    result=propose_reconstruction(p,raster([[(70,100),(130,100)],[(100,70),(100,130)]]))
    direct=[c for c in result['candidates'] if c['kind']=='continuation']
    assert len(direct)==2
    assert len([c for c in direct if c['recommended']])==1
    with pytest.raises(ValueError,match='cross'):
        apply_candidates(p,direct)


def test_real_regression_remains_unchanged_without_evidence():
    import json
    from pathlib import Path
    data=json.loads((Path(__file__).parent/'fixtures/reviewed_34_wall_snapshot.json').read_text())
    # Fixture is deliberately non-gold; run its geometry without manufacturing ink.
    geometry=Geometry(width_px=data['width_px'],height_px=data['height_px'],walls=[
        Wall(id=wid,start=Pt(x=x1,y=y1),end=Pt(x=x2,y=y2))
        for wid,x1,y1,x2,y2 in data['walls']])
    plan=from_geometry(geometry);before=plan.model_dump()
    # Existing import splits two source walls into sub-3px edges. Do not
    # silently delete source evidence to make the validator accept this case.
    with pytest.raises(ValueError,match='shorter than 3 pixels'):
        propose_reconstruction(plan,Image.new('L',(plan.width_px,plan.height_px),255))
    assert plan.model_dump()==before


def test_reconstruction_preserves_pending_opening_evidence_and_room_metadata():
    from app.plan_graph import PlanNode, PlanWall
    from app.graph_adapter import derive_faces
    plan=broken_loop();plan.width_px=400
    for name,x,y in [('a',250,20),('b',350,20),('c',350,120),('d',250,120)]:
        plan.nodes.append(PlanNode(id='room-'+name,point=Pt(x=x,y=y)))
    for a,b in [('a','b'),('b','c'),('c','d'),('d','a')]:
        plan.walls.append(PlanWall(id='room-'+a+b,start_node_id='room-'+a,end_node_id='room-'+b))
    plan.rooms=derive_faces(plan)
    plan.rooms[0].verified=True;plan.rooms[0].label='Reviewed bedroom';plan.rooms[0].evidence_ids=['human-review']
    plan.pending_openings=[Opening(id='unresolved',kind='window',wall_id='unknown',offset_m=1,width_m=1,height_m=1,sill_m=1)]
    image=Image.new('L',(400,200),255);ImageDraw.Draw(image).line([(80,20),(120,20)],fill=0,width=3)
    preview=propose_reconstruction(plan,image)
    result=apply_candidates(plan,preview['candidates'])
    assert result.pending_openings==plan.pending_openings
    assert next(r for r in result.rooms if r.id==plan.rooms[0].id)==plan.rooms[0]
    assert len(result.rooms)==2
