import hashlib
import json
from pathlib import Path
import pytest
from PIL import Image
from pydantic import ValidationError
from app.extraction_benchmark import (
    PlanPrediction,Point,Segment,OpeningLabel,image_identity,compare,
    load_prediction,save_prediction,
)
from app.extraction_exports import (
    import_normalized,normalize_florp_geometry,
)

def image(tmp_path):
    path=tmp_path/'input.png'
    Image.new('RGB',(400,200),'white').save(path)
    return path

def prediction(path,provider='truth',walls=None,rooms=None,openings=None,ppm=None):
    return PlanPrediction(provider=provider,**image_identity(path),
        walls=walls or [],rooms=rooms or [],openings=openings or [],
        px_per_meter=ppm)

def wall(x1,y1,x2,y2):
    return Segment(start=Point(x=x1,y=y1),end=Point(x=x2,y=y2))

def test_identical_geometry_scores_perfect(tmp_path):
    img=image(tmp_path)
    square=[[Point(x=x,y=y) for x,y in [(40,30),(280,30),(280,160),(40,160)]]]
    door=OpeningLabel(kind='door',start=Point(x=90,y=30),end=Point(x=130,y=30))
    gt=prediction(img,walls=[wall(40,30,280,30)],rooms=square,openings=[door],ppm=50)
    result=compare(gt,gt)
    assert result['walls']['f1']==1.
    assert result['openings']['f1']==1.
    assert result['room_area_iou']==1.
    assert result['relative_scale_error']==0.

def test_extra_wall_cannot_match_twice(tmp_path):
    img=image(tmp_path)
    gt=prediction(img,walls=[wall(40,30,280,30)])
    pp=prediction(img,'model',walls=[wall(40,30,280,30),wall(45,31,275,31)])
    result=compare(gt,pp)
    assert result['walls']['matched']==1
    assert result['walls']['precision']==.5
    assert result['walls']['recall']==1.

def test_missing_wall_and_wrong_opening_class(tmp_path):
    img=image(tmp_path)
    o=OpeningLabel(kind='door',start=Point(x=80,y=30),end=Point(x=100,y=30))
    wrong=OpeningLabel(kind='window',start=o.start,end=o.end)
    gt=prediction(img,walls=[wall(40,30,280,30)],openings=[o])
    result=compare(gt,prediction(img,'model',openings=[wrong]))
    assert result['walls']['recall']==0.
    assert result['openings']['recall']==0.

def test_no_scale_is_unknown_not_fabricated(tmp_path):
    img=image(tmp_path)
    gt=prediction(img,ppm=50)
    model=prediction(img,'model')
    assert compare(gt,model)['relative_scale_error'] is None

def test_crop_and_reencode_rejected(tmp_path):
    img=image(tmp_path)
    gt=prediction(img)
    other=prediction(img,'model')
    other.image_sha256='a'*64
    with pytest.raises(ValueError,match='mismatch'):
        compare(gt,other)

def test_invalid_geometry_rejected(tmp_path):
    img=image(tmp_path)
    with pytest.raises(ValidationError):
        prediction(img,walls=[wall(1,1,500,1)])

def test_roundtrip_and_external_import_requires_explicit_contract(tmp_path):
    img=image(tmp_path)
    model=prediction(img,'raster2seq',rooms=[
        [Point(x=20,y=20),Point(x=180,y=20),Point(x=180,y=140)]])
    export=tmp_path/'provider.json'
    save_prediction(export,model)
    assert load_prediction(export)==model
    assert import_normalized(img,export,'raster2seq')==model
    export.write_text(json.dumps({'rooms':[[[1,2],[3,4]]]}))
    with pytest.raises(ValueError,match='not normalized'):
        import_normalized(img,export,'raster2seq')

def test_florp_geometry_adapter(tmp_path):
    img=image(tmp_path)
    geom={'width_px':400,'height_px':200,
          'walls':[{'id':'w','start':{'x':20,'y':30},'end':{'x':300,'y':30}}],
          'rooms':[{'id':'r','points':[{'x':20,'y':30},{'x':300,'y':30},{'x':300,'y':150}]}]}
    result=normalize_florp_geometry(img,geom)
    assert len(result.walls)==1
    assert len(result.rooms)==1
    assert result.px_per_meter is None

def test_empty_room_sets_are_unscored_not_perfect(tmp_path):
    img=image(tmp_path)
    result=compare(prediction(img),prediction(img,'model'))
    assert result['room_area_iou'] is None
    assert result['room_count']=={'predicted':0,'ground_truth':0}

def test_missing_opening_evidence_is_unscored(tmp_path):
    img=image(tmp_path)
    result=compare(prediction(img),prediction(img,'model'))
    assert result['openings'] is None


def test_length_coverage_penalizes_tiny_fragment_of_long_wall():
    from app.extraction_benchmark import wall_length_coverage,Segment,Point
    truth=[Segment(start=Point(x=0,y=0),end=Point(x=100,y=0))]
    predicted=[Segment(start=Point(x=0,y=0),end=Point(x=10,y=0))]
    score=wall_length_coverage(truth,predicted,1)
    assert score['precision']==1
    assert score['recall']<.12


def test_opening_span_score_rejects_short_window_with_matching_center():
    from app.extraction_benchmark import PlanPrediction,OpeningLabel,Point,compare
    base=dict(provider='test',image_sha256='a'*64,width_px=200,height_px=200)
    truth=PlanPrediction(**base,openings=[OpeningLabel(kind='window',start=Point(x=20,y=20),end=Point(x=120,y=20))])
    pred=PlanPrediction(**base,openings=[OpeningLabel(kind='window',start=Point(x=50,y=20),end=Point(x=90,y=20))])
    assert compare(truth,pred,3)['opening_spans']['recall']==0
