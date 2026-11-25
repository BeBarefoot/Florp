import numpy as np

from app.ink_layers import Strips
from app.openings import Gap, _dashes
from app.photo_boundary_repair import recover_photo_boundaries
from app.plan_model import ImageTransform, Node, Opening, PlanModel, Pt, Wall


def photo_case():
    width, height = 520, 210
    coords = [(25, 35), (90, 35), (126, 35), (270, 35), (270, 185),
              (160, 185), (133, 185), (25, 185)]
    nodes = [Node(id=str(i), x=x, y=y) for i, (x, y) in enumerate(coords)]
    pairs = [(0, 1), (2, 3), (3, 4), (4, 5), (6, 7), (7, 0)]
    walls = [Wall(id=f"wall{i}", a=str(a), b=str(b), thickness_px=12)
             for i, (a, b) in enumerate(pairs)]
    windows = [Opening(id=f"win{i}", kind="window", host_wall_id=f"wall{i}",
                       offset_px=5 if i else 30, width_px=30)
               for i in range(2)]
    model = PlanModel(id="test", image_transform=ImageTransform(width=width, height=height),
                      nodes=nodes, walls=walls, openings=windows)
    image = np.full((height, width, 3), 245, dtype=np.uint8)
    image[29:42, 89:128] = (24, 201, 231)
    ink = np.zeros((height, width), dtype=bool)
    ink[36, 90:127] = True
    ink[185, 133:161] = True
    color = np.zeros_like(ink)
    color[180:190, 133:151] = True
    empty = np.zeros_like(ink)
    strips = Strips(color, empty, empty, empty, {"coloured_walls": True},
                    boundary_mask=color, structural_colour=color, ink=ink)
    return model, image, strips


def test_short_supported_breaks_form_the_indoor_room_without_moving_openings():
    plan, image, strips = photo_case()
    updated = recover_photo_boundaries(plan, image, strips)
    assert len(updated.rooms) == 1
    assert updated.rooms[0].area_px2 > 30_000
    assert len(updated.walls) == len(plan.walls) + 2
    assert updated.nodes == plan.nodes and updated.openings == plan.openings


def test_tree_fill_alone_or_an_existing_door_cannot_close_the_room():
    plan, image, strips = photo_case()
    strips.ink[36] = False
    assert recover_photo_boundaries(plan, image, strips) is plan
    strips.ink[36, 90:127] = True
    plan.openings.append(Opening(id="unhosted", kind="door", span=(Pt(x=91, y=35), Pt(x=125, y=35))))
    assert recover_photo_boundaries(plan, image, strips) is plan


def test_parallel_parking_guide_is_outside_photo_garage_door_lane():
    line = np.zeros((100, 220), dtype=bool)
    gap = Gap(True, 50, 20, 200, 12)
    for x in range(20, 200, 20):
        line[39, x:x + 8] = True
    assert _dashes(line, gap) > 0
    assert _dashes(line, gap, band_factor=.5) == 0
    line[50] = line[39]
    assert _dashes(line, gap, band_factor=.5) > 0
