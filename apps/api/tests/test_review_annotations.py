from app.providers import ProviderAuthenticationError
from app.models import WallAnnotation
from app.geometry import fallback_geometry

def test_authentication_error_is_specific():
    assert '401' in str(ProviderAuthenticationError('HTTP 401'))

def test_annotation_model():
    item=WallAnnotation(blueprint_id='test',candidate_key='1:2:3:4',label='not_wall',coordinates={'x1':1,'y1':2,'x2':3,'y2':4})
    assert item.coordinates['x2']==3

def test_unverified_fallback():
    assert fallback_geometry(400,300).px_per_meter is None
