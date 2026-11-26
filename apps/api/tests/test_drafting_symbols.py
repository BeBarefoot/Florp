import cv2
import numpy as np

from app.drafting_symbols import compound_symbols
from app.fixture_detection import furniture_symbol_hits
from app.plan_model import ImageTransform, PlanModel


def test_faded_six_seat_dining_set_keeps_its_footprint_after_rotation():
    paper = np.full((160, 180), 216, np.uint8)
    cv2.rectangle(paper, (48, 62), (117, 100), 140, 1)
    for x in (54, 76, 98):
        for y in (50, 100):
            cv2.rectangle(paper, (x, y), (x + 14, y + 12), 146, 1)
    scan = cv2.cvtColor(cv2.rotate(paper, cv2.ROTATE_90_CLOCKWISE), cv2.COLOR_GRAY2BGR)
    result = compound_symbols(scan)
    (dining,) = [s for s in result if s.kind == "dining_table"]
    assert abs(dining.position.x - 79) < 5 and abs(dining.position.y - 83) < 5
    model = PlanModel(
        id="test",
        image_transform=ImageTransform(width=160, height=180),
        room_symbols=result,
    )
    assert furniture_symbol_hits(model) == []
    model.scale.meters_per_pixel = 0.03
    (hit,) = [h for h in furniture_symbol_hits(model) if h.kind == "dining_6"]
    assert hit.rotation == 90 and 1.8 < hit.width < 2.6


def test_empty_scan_and_parallel_dimension_lines_do_not_suggest_furniture():
    paper = np.full((80, 200, 3), 225, np.uint8)
    for y in (20, 25, 63):
        cv2.line(paper, (2, y), (194, y), (125, 125, 125), 1)
    assert compound_symbols(paper) == []


def test_kitchen_basin_requires_a_second_rim_and_a_nearby_hob():
    from app.drafting_symbols import counter_basins
    from app.plan_model import RoomSymbol, Pt

    image = np.full((140, 280, 3), 218, np.uint8)
    hob = RoomSymbol(kind="cooktop", position=Pt(x=70, y=62), width_px=40, depth_px=40)
    assert counter_basins(image, [hob]) == []
    cv2.rectangle(image, (143, 46), (179, 78), (120, 120, 120), 1)
    cv2.rectangle(image, (146, 49), (176, 75), (120, 120, 120), 1)
    assert counter_basins(image, []) == []
    (sink,) = counter_basins(image, [hob])
    assert abs(sink.position.x - 161) < 3 and abs(sink.position.y - 62) < 3


def test_canopies_require_texture_inside_the_green_region():
    from app.drafting_symbols import tree_symbols

    image = np.full((180, 200, 3), 238, np.uint8)
    cv2.circle(image, (61, 80), 22, (38, 111, 40), -1)
    assert tree_symbols(image) == []
    for i in range(43, 82, 5):
        cv2.circle(image, (i, 80), 5, (17, 49, 23), -1)
    (tree,) = tree_symbols(image)
    assert tree.kind == "tree" and abs(tree.position.x - 61) < 2


def test_bar_counter_requires_an_outline_beside_the_stools():
    from app.drafting_symbols import bar_counters
    from app.plan_model import RoomSymbol, Pt

    image = np.full((160, 240, 3), 232, np.uint8)
    stools = RoomSymbol(
        kind="bar_stools", position=Pt(x=120, y=70), width_px=120, depth_px=32
    )
    cv2.line(image, (60, 72), (180, 72), (78, 78, 78), 1)
    assert bar_counters(image, [stools]) == []
    cv2.rectangle(image, (60, 72), (180, 104), (78, 78, 78), 1)
    (bar,) = bar_counters(image, [stools])
    assert bar.kind == "bar_counter" and abs(bar.position.y - 88) < 3
