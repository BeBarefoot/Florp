"""A phone-photo-style synthetic plan with a mixed-colour wall network."""
from PIL import Image, ImageDraw
from shapely.geometry import Point, Polygon

from app.workspace_worker import build


def test_mixed_colour_rooms_do_not_turn_solid_walls_into_windows(tmp_path):
    image = Image.new('RGB', (600, 860), '#eeeae1')
    draw = ImageDraw.Draw(image)
    draw.rectangle((90, 130, 500, 735), outline='#b78085', width=13)
    draw.line((292, 130, 292, 735), fill='#394f83', width=17)
    draw.line((90, 420, 292, 420), fill='#b78085', width=12)
    # A dimension line crosses the lower room and both outside walls.
    for y in (102, 690):
        draw.line((60, y, 550, y), fill='#646464', width=1)
        for x in (90, 292, 500):
            draw.line((x, y - 5, x, y + 5), fill='#646464')
        draw.text((164, y - 15), '290', fill='#424242')
    draw.rectangle((125, 180, 195, 320), outline='#777777')
    draw.rectangle((130, 185, 190, 210), outline='#777777')
    for x in range(360, 450, 8):
        draw.line((x, 530, x + 15, 550), fill='#808080')
    for x in range(10, 580, 80):
        draw.line((x, 70, x + 46, 70), fill='#a14145', width=4)
    path = tmp_path / 'synthetic.jpg'
    image.save(path, quality=83)
    model = build(str(path), plan_id='fixture')
    rooms = [Polygon([(p.x, p.y) for p in room.polygon]) for room in model.rooms]
    interiors = [Point(188, 295), Point(180, 610), Point(390, 390)]
    assert len(rooms) == 3
    assert sorted(tuple(i for i, p in enumerate(interiors) if r.contains(p)) for r in rooms) == [(0,), (1,), (2,)]
    assert not model.openings
