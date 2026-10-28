from copy import deepcopy
import pytest
from app.geometry import Geometry, Wall, Pt, Opening, fallback_geometry
from app.plan_graph import CanonicalPlan, PlanNode, PlanWall
from app.graph_adapter import from_geometry, to_geometry
from app.graph_validation import validate_plan
from app.graph_operations import GraphOperation, apply_operation


def wall(name, a, b):
    return Wall(id=name, start=Pt(x=a[0], y=a[1]), end=Pt(x=b[0], y=b[1]))


def square():
    return Geometry(width_px=400, height_px=400, walls=[
        wall('top',(50,50),(250,50)),
        wall('right',(250,50),(250,250)),
        wall('bottom',(250,250),(50,250)),
        wall('left',(50,250),(50,50)),
    ])


def test_closed_rectangle_produces_supported_face():
    plan = from_geometry(square())
    assert len(plan.nodes) == 4
    assert len(plan.walls) == 4
    assert len(plan.rooms) == 1
    assert len(plan.rooms[0].boundary) == 4
    assert validate_plan(plan) == []


def test_missing_boundary_does_not_fabricate_room():
    g = square()
    g.walls.pop()
    plan = from_geometry(g)
    assert plan.rooms == []
    assert len(plan.walls) == 3


def test_shared_t_junction_splits_host_without_fake_gap():
    g = Geometry(width_px=400, height_px=400, walls=[
        wall('horizontal',(20,100),(300,100)),
        wall('branch',(160,100),(160,250)),
    ])
    plan = from_geometry(g)
    horizontal = [w for w in plan.walls if w.source_wall_id == 'horizontal']
    assert len(horizontal) == 2
    branch = next(w for w in plan.walls if w.source_wall_id == 'branch')
    assert branch.start_node_id in {w.start_node_id for w in horizontal} | {w.end_node_id for w in horizontal}
    assert len(plan.rooms) == 0


def test_move_junction_is_atomic_and_source_unchanged():
    plan = from_geometry(square())
    original = plan.model_dump()
    node = next(n for n in plan.nodes if n.point.x == 50 and n.point.y == 50)
    changed = apply_operation(plan, GraphOperation(kind='move_junction',node_id=node.id,point=Pt(x=55,y=55)))
    assert plan.model_dump() == original
    assert next(n for n in changed.nodes if n.id == node.id).point == Pt(x=55,y=55)
    assert sum(node.id in (w.start_node_id,w.end_node_id) for w in changed.walls) == 2
    assert len(changed.rooms) == 1


def test_split_wall_preserves_and_remaps_opening():
    g = Geometry(width_px=400,height_px=200,px_per_meter=10,scale_source='user_confirmed',
       walls=[wall('host',(10,100),(190,100))],
       openings=[Opening(id='window',kind='window',wall_id='host',
                         offset_m=12,width_m=2,height_m=1,sill_m=1)])
    plan = from_geometry(g)
    result = apply_operation(plan, GraphOperation(kind='split_wall',wall_id='host',point=Pt(x=100,y=100)))
    assert len(result.walls) == 2
    assert result.openings[0].id == 'window'
    assert result.openings[0].wall_id != 'host'
    assert result.openings[0].offset_m == pytest.approx(3)
    assert validate_plan(result) == []


def test_split_through_opening_rejected_without_mutation():
    g = Geometry(width_px=400,height_px=200,px_per_meter=10,scale_source='user_confirmed',
       walls=[wall('host',(10,100),(190,100))],
       openings=[Opening(id='door',kind='door',wall_id='host',offset_m=8,width_m=2,height_m=2)])
    plan = from_geometry(g)
    old = plan.model_dump()
    with pytest.raises(ValueError,match='cut through opening'):
        apply_operation(plan,GraphOperation(kind='split_wall',wall_id='host',point=Pt(x=100,y=100)))
    assert plan.model_dump() == old


def test_nearby_parallel_lines_remain_separate():
    g = Geometry(width_px=400,height_px=200,walls=[
        wall('a',(10,50),(200,50)),wall('b',(10,54),(200,54))])
    plan = from_geometry(g)
    assert len(plan.nodes) == 4
    assert plan.rooms == []


def test_serialization_and_provenance_roundtrip():
    g = square()
    plan = from_geometry(g)
    restored = CanonicalPlan.model_validate_json(plan.model_dump_json())
    assert restored == plan
    assert restored.provenance['adapter'] == 'legacy-geometry-v1'
    assert {w.source_wall_id for w in restored.walls} == {w.id for w in g.walls}
    assert {w.id for w in to_geometry(restored).walls} == {w.id for w in g.walls}


def test_legacy_unconfirmed_scale_keeps_opening_evidence():
    g = Geometry(width_px=400,height_px=200,walls=[wall('host',(10,100),(190,100))],
       openings=[Opening(id='door',kind='door',wall_id='host',offset_m=1,width_m=.8,height_m=2)])
    before = g.model_dump()
    plan = from_geometry(g)
    assert len(plan.pending_openings) == 1
    assert len(plan.openings) == 0
    assert plan.pending_openings[0].id == 'door'
    with pytest.raises(ValueError,match='pending legacy opening'):
        to_geometry(plan)
    assert g.model_dump() == before


def test_invalid_edits_do_not_change_original_plan():
    plan = from_geometry(square())
    snapshot = deepcopy(plan.model_dump())
    target = plan.walls[0]
    p = next(n.point for n in plan.nodes if n.id == target.end_node_id)
    with pytest.raises(ValueError,match='shorter than 3 pixels'):
        apply_operation(plan,GraphOperation(kind='move_junction',node_id=target.start_node_id,point=p))
    removed = apply_operation(plan,GraphOperation(kind='remove_wall',wall_id=target.id))
    assert target.id not in {w.id for w in removed.walls}
    assert removed.rooms == []
    assert plan.model_dump() == snapshot


def test_opening_attachment_requires_confirmed_scale():
    p = from_geometry(Geometry(width_px=400,height_px=200,walls=[wall('a',(10,50),(200,50))]))
    new = dict(id='door',wall_id='a',kind='door',offset_m=1,width_m=.8,height_m=2)
    from app.plan_graph import PlanOpening
    with pytest.raises(ValueError,match='user-confirmed'):
        apply_operation(p,GraphOperation(kind='attach_opening',opening=PlanOpening(**new)))


def test_starting_placeholder_does_not_become_verified_room_evidence():
    plan = from_geometry(fallback_geometry(992,440))
    assert plan.rooms == []

def test_verified_room_boundary_is_protected():
    plan = from_geometry(square())
    plan.rooms[0].verified = True
    with pytest.raises(ValueError,match='verified room boundary'):
        apply_operation(plan,GraphOperation(kind='remove_wall',wall_id=plan.walls[0].id))


def test_add_wall_completes_room_without_auto_bridging_gap():
    g = square()
    g.walls.pop()
    plan = from_geometry(g)
    added = apply_operation(plan,GraphOperation(kind='add_wall',
                 start=Pt(x=50,y=250),end=Pt(x=50,y=50)))
    assert len(added.rooms)==1
    assert len(added.walls)==4

def test_stale_legacy_room_polygons_never_override_graph_floors():
    from app.geometry import Room
    g = square()
    g.rooms = [Room(id='legacy-unverified',points=[
        Pt(x=60,y=60),Pt(x=100,y=60),Pt(x=100,y=100)])]
    plan = from_geometry(g)
    assert len(plan.legacy_rooms) == 1
    assert to_geometry(plan).rooms == []
    converted = to_geometry(plan,include_derived_rooms=True)
    assert len(converted.rooms) == 1
    assert converted.rooms[0].id.startswith('face-')
    assert len(converted.rooms[0].points) == 4

def test_split_at_existing_endpoint_reuses_shared_junction():
    plan=CanonicalPlan(width_px=300,height_px=200,nodes=[
        PlanNode(id='a',point=Pt(x=10,y=100)),
        PlanNode(id='b',point=Pt(x=190,y=100)),
        PlanNode(id='joint',point=Pt(x=100,y=100)),
        PlanNode(id='c',point=Pt(x=100,y=160))],
      walls=[PlanWall(id='horizontal',start_node_id='a',end_node_id='b'),
             PlanWall(id='branch',start_node_id='joint',end_node_id='c')])
    result=apply_operation(plan,GraphOperation(
        kind='split_wall',wall_id='horizontal',point=Pt(x=100,y=100)))
    assert len(result.nodes)==4
    assert len([w for w in result.walls if 'joint' in (w.start_node_id,w.end_node_id)])==3

def test_crossing_added_wall_requires_explicit_junction():
    plan = from_geometry(Geometry(width_px=300,height_px=200,
                                  walls=[wall('host',(10,100),(190,100))]))
    before = plan.model_dump()
    with pytest.raises(ValueError,match='cross without a shared junction'):
        apply_operation(plan,GraphOperation(kind='add_wall',
            start=Pt(x=100,y=40),end=Pt(x=100,y=160)))
    assert plan.model_dump()==before


def test_crossing_wall_can_be_added_after_explicit_split():
    plan = from_geometry(Geometry(width_px=300,height_px=200,
                                  walls=[wall('host',(10,100),(190,100))]))
    split = apply_operation(plan,GraphOperation(kind='split_wall',
                                             wall_id='host',point=Pt(x=100,y=100)))
    branch = apply_operation(split,GraphOperation(kind='add_wall',
                         start=Pt(x=100,y=100),end=Pt(x=100,y=160)))
    joint = next(n.id for n in branch.nodes if n.point==Pt(x=100,y=100))
    assert sum(joint in (w.start_node_id,w.end_node_id) for w in branch.walls)==3


def test_short_source_subdivisions_survive_import_without_allowing_collapsed_edges():
    g=Geometry(width_px=300,height_px=200,walls=[
        wall('host',(10,100),(200,100)),wall('branch',(12,100),(12,180))])
    plan=from_geometry(g)
    assert validate_plan(plan)==[]
    host=[w for w in plan.walls if w.source_wall_id=='host']
    assert len(host)==2
    assert len(to_geometry(plan).walls)==3
    before=plan.model_dump()
    # User drawing/movement still refuses newly created short walls.
    with pytest.raises(ValueError,match='short wall'):
        apply_operation(plan,GraphOperation(kind='add_wall',start=Pt(x=30,y=30),end=Pt(x=31,y=30)))
    tiny=host[0]
    nodes={n.id:n for n in plan.nodes}
    nodes[tiny.end_node_id].point=nodes[tiny.start_node_id].point.model_copy()
    assert any('zero-length' in issue for issue in validate_plan(plan))
