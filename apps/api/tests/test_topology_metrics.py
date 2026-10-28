import json
from pathlib import Path
import pytest
from app.geometry import Geometry, Wall, Pt, Opening
from app.graph_adapter import from_geometry
from app.topology_metrics import TopologyCase, compare_topology, structural_health


SHA = 'a'*64


def segment(name,a,b):
    return Wall(id=name,start=Pt(x=a[0],y=a[1]),end=Pt(x=b[0],y=b[1]))


def complete():
    return Geometry(width_px=400,height_px=400,walls=[
        segment('top',(50,50),(250,50)),
        segment('right',(250,50),(250,250)),
        segment('bottom',(250,250),(50,250)),
        segment('left',(50,250),(50,50))])


def case(g, *, gold=False, sha=SHA):
    return TopologyCase(source_preview_sha256=sha,
                        provider='human-review' if gold else 'candidate',
                        gold_standard=gold,plan=from_geometry(g))


def test_identical_verified_reference_scores_perfectly():
    gold=case(complete(),gold=True)
    pred=case(complete())
    results=compare_topology(gold,pred)
    assert results['junctions']['f1']==1
    assert results['wall_adjacency_edges']['f1']==1
    assert results['room_regions_at_iou_0_5']['f1']==1
    assert results['reference_health']['connected_components']==1


def test_missing_wall_penalized_even_when_all_junctions_match():
    reference=complete()
    incomplete=complete()
    incomplete.walls.pop()
    results=compare_topology(case(reference,gold=True),case(incomplete))
    assert results['junctions']['f1']==1
    assert results['wall_adjacency_edges']['f1']<1
    assert results['room_regions_at_iou_0_5']['recall']==0


def test_mismatched_image_and_unreviewed_truth_rejected():
    gold=case(complete(),gold=True)
    with pytest.raises(ValueError,match='Image SHA256 mismatch'):
        compare_topology(gold,case(complete(),sha='b'*64))
    with pytest.raises(ValueError,match='not independently confirmed'):
        compare_topology(case(complete()),case(complete()))


def test_opening_host_wrong_while_wall_topology_is_right():
    g=complete()
    g.px_per_meter=10
    g.scale_source='user_confirmed'
    g.openings=[Opening(id='window',kind='window',wall_id='top',
                       offset_m=5,width_m=3,height_m=1,sill_m=1)]
    pred=g.model_copy(deep=True)
    pred.openings[0].wall_id='bottom'
    report=compare_topology(case(g,gold=True),case(pred))
    assert report['wall_adjacency_edges']['f1']==1
    assert report['opening_identity_recall']==1
    assert report['opening_host_accuracy']==0


def test_real_reviewed_34_wall_export_is_not_auto_promoted_to_gold():
    path=Path(__file__).parent/'fixtures'/'reviewed_34_wall_snapshot.json'
    fixture=json.loads(path.read_text())
    assert fixture['ground_truth_status']=='not_ground_truth_reviewed_export'
    assert fixture['reviewed_label_counts']['accept']==34
    assert fixture['reviewed_label_counts']['door']+fixture['reviewed_label_counts']['window']==21
    walls=[segment(name,(x1,y1),(x2,y2))
           for name,x1,y1,x2,y2 in fixture['walls']]
    g=Geometry(width_px=fixture['width_px'],height_px=fixture['height_px'],
               walls=walls)
    plan=from_geometry(g)
    assert {w.source_wall_id for w in plan.walls}=={w.id for w in walls}
    assert plan.rooms==[]  # no enclosed source-wall cycle, no fabricated floors
    assert plan.px_per_meter is None
    assert plan.openings==[]
    health=structural_health(plan)
    assert health['connected_components']>1
    assert health['supported_room_cycles']==0
