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
