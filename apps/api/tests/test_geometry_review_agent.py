import numpy as np
import pytest
from app.geometry import Geometry,Wall,Pt
from app.evidence_fusion import FusedCandidate
from app.geometry_review_agent import review_geometry

def pt(x,y):return Pt(x=x,y=y)
def geometry():
    return Geometry(width_px=320,height_px=200,walls=[
        Wall(id='model-a',start=pt(50,20),end=pt(50,90)),
        Wall(id='model-b',start=pt(150,20),end=pt(150,90))])
def candidate(id='mask-gap',a=None,b=None):
    return FusedCandidate(id=id,start=a or pt(50,90),end=b or pt(150,90),
        sources=['yytsi_mask'],mask_support=.97,category='yytsi_only')

def test_proposes_evidence_backed_connection_without_mutating_geometry():
    g=geometry()
    mask=np.zeros((200,320),dtype=np.uint8)
    mask[88:93,50:151]=255
    before=g.model_dump()
    items=review_geometry(g,[candidate()],mask)
    assert len(items)==1
    assert items[0].candidate_id=='mask-gap'
    assert items[0].priority>.7
    assert 'Connects two' in items[0].reason
    assert g.model_dump()==before

def test_rejects_unsupported_furniture_and_unconnected_segments():
    g=geometry()
    empty=np.zeros((200,320),dtype=np.uint8)
    assert review_geometry(g,[candidate()],empty)==[]
    mask=np.zeros((200,320),dtype=np.uint8)
    mask[118:123,180:280]=255
    floating=candidate(a=pt(180,120),b=pt(280,120))
    assert review_geometry(g,[floating],mask)==[]

def test_rejects_duplicate_existing_wall():
    g=geometry()
    mask=np.zeros((200,320),dtype=np.uint8)
    mask[18:23,50:151]=255
    already=candidate(a=pt(50,20),b=pt(50,90))
    mask[20:91,48:53]=255
    assert review_geometry(g,[already],mask)==[]

def test_invalid_mask_dimensions_rejected():
    with pytest.raises(ValueError,match='dimensions'):
        review_geometry(geometry(),[candidate()],np.zeros((20,20),dtype=np.uint8))
