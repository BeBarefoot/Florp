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


def test_pale_capped_pier_requires_two_faces_and_a_solid_host():
    from app.capped_returns import faint_painted_returns, restore_returns
    image = np.full((120,180,3), 210, np.uint8)
    image[30:80,85:92] = (146,148,161)
    image[30:80,85] = image[30:80,91] = image[79,85:92] = 60
    nodes = [Node(id=str(i),x=x,y=y) for i,(x,y) in enumerate(((10,26),(160,26),(160,108)))]
    plan = PlanModel(id="case",image_transform=ImageTransform(width=180,height=120),
                     nodes=nodes,walls=[Wall(id="top",a="0",b="1",thickness_px=10),
                                        Wall(id="side",a="1",b="2",thickness_px=10)])
    result = restore_returns(plan,faint_painted_returns(image,10))
    assert any(abs(n.x-88)<2 and abs(n.y-79)<2 for n in result.nodes)
    image[30:79,91] = 210
    assert restore_returns(plan,faint_painted_returns(image,10)) is plan


def test_swing_drawn_on_continuous_concrete_needs_a_leaf_and_matching_arc():
    import cv2
    from app.painted_openings import painted_swings
    nodes=[Node(id=str(i),x=x,y=y) for i,(x,y) in enumerate([(110,10),(110,170),(10,10),(10,170)])]
    walls=[Wall(id="painted",a="0",b="1",material="concrete",thickness_px=12),
           Wall(id="other",a="2",b="3",thickness_px=8)]
    doors=[Opening(id=f"d{i}",kind="door",host_wall_id="other",width_px=40,
                   offset_px=i*60,status="confirmed") for i in range(2)]
    plan=PlanModel(id="case",image_transform=ImageTransform(width=200,height=190),nodes=nodes,walls=walls,openings=doors)
    image=np.full((190,200,3),214,np.uint8)
    cv2.line(image,(110,10),(110,170),(145,77,50),10)
    cv2.line(image,(104,60),(64,60),(80,80,80),1)
    assert painted_swings(plan,image) is plan
    cv2.ellipse(image,(104,60),(40,40),0,90,180,(80,80,80),1)
    changed=painted_swings(plan,image)
    assert len(changed.openings)==3
    door=changed.openings[-1]
    assert door.host_wall_id=="painted" and door.status=="proposed"
    assert abs(door.offset_px-50)<3 and abs(door.width_px-40)<4


def test_dimension_line_must_continue_past_both_door_jambs():
    import cv2
    from app.painted_openings import remove_dimension_hosts
    plan,image,strips=photo_case()
    # Use a short inferred host inside the plan.
    plan.walls=plan.walls[:1]
    plan.openings=[Opening(id="door",kind="door",host_wall_id="wall0",offset_px=5,width_px=55)]
    for node in plan.nodes[:2]:
        node.x+=100
    cv2.line(image,(70,35),(230,35),(60,60,60),1)
    assert remove_dimension_hosts(plan,image,strips).walls==[]
    image[32:39,195:]=245
    assert remove_dimension_hosts(plan,image,strips) is plan
