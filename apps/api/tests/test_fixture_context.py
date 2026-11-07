from app.fixture_detection import Hit
from app.fixture_weights import contextual_hits
from app.plan_model import PlanModel
from test_plan_derive import two_rooms


def model():
    data=two_rooms()
    data['scale']={'reference':{'p1':{'x':100,'y':100},'p2':{'x':400,'y':100},'lengthMeters':3}}
    data['envelope']=[{'x':100,'y':100},{'x':400,'y':100},{'x':400,'y':300},{'x':100,'y':300}]
    return PlanModel.model_validate(data)


def test_weight_context_rejects_site_ink_wall_overlap_and_duplicates():
    hits=[Hit('toilet',.8,180,200,.4,.6,0), Hit('toilet',.6,181,201,.4,.6,0),
          Hit('bed',.9,600,200,1,2,0),Hit('wardrobe',.8,250,200,.15,1,0)]
    kept=contextual_hits(hits,model())
    assert kept == [hits[0]]


def test_distinct_objects_remain_and_no_geometry_is_changed():
    m=model();before=m.dump()
    hits=[Hit('toilet',.8,180,200,.4,.6,0),Hit('toilet',.8,320,200,.4,.6,0)]
    assert contextual_hits(hits,m)==hits
    assert m.dump()==before


def test_stair_footprint_is_not_a_fixture():
    m=model()
    from app.plan_model import Stair, Pt
    m.stairs=[Stair(id='s',layout='l',treads=[[Pt(x=150,y=y),Pt(x=210,y=y),Pt(x=210,y=y+26),Pt(x=150,y=y+26)] for y in (160,186,212)])]
    assert contextual_hits([Hit('toilet',.8,180,200,.4,.6,0)],m)==[]
