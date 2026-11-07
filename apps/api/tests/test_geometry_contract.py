"""Analytical cases also consumed by TypeScript: no generated-model accuracy claim."""
import json
from pathlib import Path
import pytest
from shapely.geometry import Polygon, box
from app.plan_model import PlanModel
from app.plan_derive import derive

CASES = json.loads((Path(__file__).parents[3] / 'tests/fixtures/geometry-contract.json').read_text())

@pytest.mark.parametrize('case', CASES, ids=lambda c:c['name'])
def test_room_metric_contract(case):
    model = derive(PlanModel.model_validate(case['model']))
    assert [r.area_px2 for r in model.rooms] == pytest.approx(case['expectedAreasPx2'])
    assert model.scale.meters_per_pixel == .01
    for room, bounds in zip(model.rooms, case['expectedBoundsPx']):
        polygon = Polygon([(p.x,p.y) for p in room.polygon])
        assert polygon.is_valid
        assert polygon.equals(box(*bounds))
        assert polygon.area == pytest.approx(room.area_px2)
    assert sum(r.area_px2 for r in model.rooms)*.01**2 == pytest.approx(sum(case['expectedAreasPx2'])/10000)


def test_room_merge_clears_ambiguous_semantics():
    model = derive(PlanModel.model_validate(CASES[0]['model']))
    model.rooms[0].label = 'Bedroom'
    model.rooms[0].room_type = 'bedroom'
    model.rooms[0].ceiling_height_m = 3.1
    # Move the partition; unchanged boundary identities retain semantics.
    for n in model.nodes:
        if n.id in ('n1','n4'): n.x = 280
    moved = derive(model)
    assert moved.rooms[0].label == 'Bedroom'
    assert moved.rooms[0].ceiling_height_m == 3.1
    moved.walls = [w for w in moved.walls if w.id != 'w6']
    merged = derive(moved)
    assert len(merged.rooms) == 1
    assert merged.rooms[0].needs_semantic_review
    assert merged.rooms[0].label is None and merged.rooms[0].room_type is None
