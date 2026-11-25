import cv2
from app.config import settings
from app.floor_pair import name_level
from test_plan_api import client
from test_stair_detection import drawing


def test_unordered_pair_site_and_stair_review(client, monkeypatch, tmp_path):
    c, upper = client
    monkeypatch.setattr(settings, 'storage_path', str(tmp_path))
    pid = c.get('/projects').json()[0]['id']
    path = f'/projects/{pid}/floor-pair'
    image = drawing()
    image[20:150, 15:160] = (115, 182, 135)
    image[45:110, 45:110] = 234  # Patio inside the lawn.
    ok, data = cv2.imencode('.jpg', image)
    assert ok
    lower = c.post(f'/projects/{pid}/blueprints', files={'file': ('photo.jpg', data.tobytes(), 'image/jpeg')}).json()['id']
    yard = c.get(f'/blueprints/{lower}/plan/yard')
    assert yard.status_code == 200
    assert len(yard.json()) == 1 and yard.json()[0]['holes']
    assert c.get(f'/blueprints/{upper}/plan/yard').json() == []
    for a,b in [(upper,lower),(lower,upper)]:
        result = c.get(path+'/suggestions', params={'a':a,'b':b}).json()
        assert result['first'] == lower
        assert not result['regions'][upper]
        regions = result['regions'][lower]
        assert {r['kind'] for r in regions} == {'garden','stairs'}
        assert next(r for r in regions if r['kind']=='garden')['holes']
    # Both floors have a stair in this second pair, but their depictions differ.
    ok, upper_bytes = cv2.imencode('.png', drawing(double=True))
    assert ok
    upstairs = c.post(f'/projects/{pid}/blueprints', files={'file': ('scan.png', upper_bytes.tobytes(), 'image/png')}).json()['id']
    both = c.get(path+'/suggestions',params={'a':upstairs,'b':lower}).json()
    assert both['first'] == lower
    assert [r['kind'] for r in both['regions'][upstairs]] == ['stairs']
    assert {r['kind'] for r in both['regions'][lower]} == {'stairs','garden'}
    pair = {'first':lower,'second':upper,'regions':result['regions']}
    assert c.put(path,json=pair).status_code == 200
    crossed = {'kind':'garden','points':[[0,0],[1,1],[0,1],[1,0]]}
    assert c.put(path,json={**pair,'regions':{upper:[],lower:[crossed]}}).status_code == 422
    assert c.get(path).json()['first'] == lower
    assert c.put(path,json={**pair,'second':lower}).status_code == 422
    other = c.post('/projects',json={'title':'Other'}).json()['id']
    assert c.put(f'/projects/{other}/floor-pair',json=pair).status_code == 404
    assert name_level('second_floor.jpg') == 2
    assert name_level('קומת קרקע.png') == 1


def test_faded_yard_around_patio_and_tinted_paper():
    import numpy as np
    from shapely.geometry import Point, Polygon
    from app.gardens import detect_gardens

    sheet = np.full((280, 700, 3), (224, 228, 226), np.uint8)
    assert detect_gardens(sheet) == []
    sheet[10:265, 8:152] = (204, 217, 212)
    sheet[35:240, 48:142] = (206, 211, 228)
    regions = detect_gardens(sheet)
    assert len(regions) == 2
    yard = Polygon(regions[0]['points'], regions[0]['holes'])
    assert yard.contains(Point(20/700, 150/280))
    assert not yard.contains(Point(90/700, 150/280))
    assert regions[1]["surface"] == "paving"
    patio = Polygon(regions[1]['points'], regions[1]['holes'])
    assert patio.contains(Point(90/700, 150/280))
    assert patio.intersection(yard).area == 0


def test_open_sided_patio_keeps_its_surface_and_rejects_unrelated_warm_fill():
    import numpy as np
    from shapely.geometry import Point, Polygon
    from app.gardens import detect_gardens

    sheet = np.full((408, 1100, 3), (174, 177, 179), np.uint8)
    sheet[5:393, 10:240] = (153, 181, 174)
    sheet[44:334, 75:241] = (147, 160, 176)
    sheet[90:270, 310:700] = (147, 160, 176)  # Indoors, separated from the lawn.
    cv2.line(sheet, (1, 120), (1000, 120), (65, 65, 65), 3)
    cv2.line(sheet, (1, 313), (1000, 313), (65, 65, 65), 2)
    areas = detect_gardens(sheet)
    assert len(areas) == 2
    patio = next(r for r in areas if r.get("surface") == "paving")
    shape = Polygon(patio["points"], patio["holes"])
    assert shape.contains(Point(175/1100, 250/408))
    assert not shape.contains(Point(220/1100, 350/408))
    assert not shape.contains(Point(450/1100, 150/408))
