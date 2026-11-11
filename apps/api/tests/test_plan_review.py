import io
import json
import zipfile
import pytest
from sqlmodel import Session, select
from app import main
from app.models import PlanReview
from test_plan_api import client, plan, reference


def body(revision=1):
    return dict(revision=revision, topology=True, openings=True, scale=True, elevations='assumed')


def test_review_is_bound_to_revision_and_can_be_reopened(client):
    c, bid = client
    url = f'/blueprints/{bid}/plan'
    assert c.put(url, json={'expectedRevision':0,'model':plan(scale=reference())}).status_code == 200
    initial = c.get(url+'/review').json()
    assert initial['status'] == 'draft' and initial['blockers'] == []
    accepted = c.post(url+'/review', json=body())
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()['status'] == 'reviewed'
    assert accepted.json()['elevations'] == 'assumed'
    assert c.post(url+'/review', json={**body(),'topology':False}).status_code == 422
    assert c.put(url, json={'expectedRevision':1,'model':plan(scale=reference())}).status_code == 200
    assert c.get(url+'/review').json()['status'] == 'draft'
    assert c.get(url+'/review?revision=1').json()['status'] == 'reviewed'
    assert c.post(url+'/review', json=body()).status_code == 409
    assert c.post(url+'/review', json=body(2)).status_code == 200
    assert c.request('DELETE',url+'/review',json={'revision':2}).json()['status'] == 'draft'
    with Session(main.engine) as session:
        receipts = session.exec(select(PlanReview).where(PlanReview.blueprint_id==bid)).all()
        assert len(receipts) == 3 and sum(r.accepted for r in receipts) == 2


@pytest.mark.parametrize('problem', ['scale','proposed','overlap','crossing','zero'])
def test_api_cannot_accept_known_geometry_problems(client, problem):
    c, bid = client
    model = plan(scale=reference())
    if problem == 'scale':
        model.pop('scale')
    if problem in ('proposed','overlap'):
        opening = dict(id='o',kind='door',hostWallId='w0',offsetPx=100,widthPx=90,status='proposed' if problem=='proposed' else 'confirmed')
        model['openings']=[opening]
        if problem == 'overlap':model['openings'].append({**opening,'id':'o2','offsetPx':150})
    if problem in ('crossing','zero'):
        model['nodes'] += [dict(id='extra1',x=400,y=50),dict(id='extra2',x=400,y=550 if problem=='crossing' else 50)]
        model['walls'].append(dict(id='extra',a='extra1',b='extra2',thicknessPx=10))
    url = f'/blueprints/{bid}/plan'
    saved = c.put(url,json={'expectedRevision':0,'model':model})
    assert saved.status_code == 200, saved.text
    result = c.post(url+'/review',json=body())
    assert result.status_code == 422
    assert c.get(url+'/review').json()['status'] == 'draft'


def test_export_includes_exact_revision_review_status(client):
    c,bid=client
    url=f'/blueprints/{bid}/plan'
    c.put(url,json={'expectedRevision':0,'model':plan(scale=reference())})
    c.post(url+'/review',json=body())
    response=c.get(url+'/export')
    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        reports=[json.loads(archive.read(name)) for name in archive.namelist() if name.endswith('.json')]
    assert any(r.get('architectureReview',{}).get('status')=='reviewed' and r['revision']==1 for r in reports)
