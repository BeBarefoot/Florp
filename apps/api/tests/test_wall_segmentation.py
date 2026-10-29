import numpy as np
import pytest
from app.wall_segmentation import mask_centerlines, propose_mask_walls
from app.geometry import Geometry, Wall, Pt

def test_empty_wall_mask_does_not_invent_geometry():
    report=mask_centerlines(np.zeros((180,320),dtype=np.uint8))
    assert report.line_count==0
    assert report.coverage_fraction==0

def test_thick_horizontal_wall_mask_produces_supported_lines():
    mask=np.zeros((180,320),dtype=np.uint8)
    mask[70:84,20:280]=255
    report=mask_centerlines(mask,min_length=60)
    assert report.coverage_fraction>0
    assert report.line_count>0
    assert all(abs(line.y2-line.y1)<=max(1,abs(line.x2-line.x1)*.16) for line in report.lines)

def test_furniture_like_full_mask_is_rejected():
    mask=np.ones((100,100),dtype=np.uint8)*255
    with pytest.raises(ValueError,match='covers most'):
        mask_centerlines(mask)

def test_mask_proposal_does_not_preserve_incorrect_old_wall_ids():
    from app.wall_segmentation import WallMaskReport, MaskLine
    original=Geometry(width_px=320,height_px=180,walls=[
        Wall(id='model-8',start=Pt(x=5,y=5),end=Pt(x=40,y=5))])
    report=WallMaskReport(coverage_fraction=.01,line_count=1,lines=[
        MaskLine(x1=20,y1=70,x2=280,y2=70,support=1.)])
    draft=propose_mask_walls(original,report)
    assert [wall.id for wall in draft.walls]==['mask-0']
    assert original.walls[0].id=='model-8'
    assert draft.structure_reviewed is False

def test_mask_run_recovers_interior_wall_when_hough_returns_none(monkeypatch):
    from app import wall_segmentation
    monkeypatch.setattr(wall_segmentation.cv2,'HoughLinesP',lambda *args,**kwargs:None)
    mask=np.zeros((160,320),dtype=np.uint8)
    mask[30:33,50:260]=255  # three-pixel wall, missed by Hough
    result=mask_centerlines(mask,min_length=50)
    assert any(abs(line.y2-line.y1)<=1 and abs(line.x2-line.x1)>=190
               for line in result.lines)
    assert result.coverage_fraction>0

def test_unsupported_short_mask_does_not_invent_wall(monkeypatch):
    from app import wall_segmentation
    monkeypatch.setattr(wall_segmentation.cv2,'HoughLinesP',lambda *args,**kwargs:None)
    mask=np.zeros((160,320),dtype=np.uint8)
    mask[40:43,50:67]=255
    result=mask_centerlines(mask,min_length=50)
    assert result.line_count==0


@pytest.mark.parametrize('fault',[None,'padding','source','count','nonfinite','missing'])
def test_inference_masks_are_bound_to_source_pixels(monkeypatch,tmp_path,fault):
    from types import SimpleNamespace
    from app import wall_segmentation as ws
    from app.pretrained_detector import DetectorUnavailable
    weights=tmp_path/'segment.pt';weights.write_bytes(b'test double, not model weights')
    monkeypatch.setattr(ws.settings,'wall_segmentation_weights',str(weights))
    mask=np.zeros((1,40,100),dtype='float32');mask[0,12:15,20:80]=1
    if fault=='padding':mask=np.pad(mask,((0,0),(30,30),(0,0)))
    if fault=='nonfinite':mask[0,0,0]=np.nan
    tensor=SimpleNamespace(cpu=lambda:SimpleNamespace(numpy=lambda:mask))
    result=SimpleNamespace(orig_shape=(41,100) if fault=='source' else (40,100),names={0:'wall'},
        masks=None if fault=='missing' else SimpleNamespace(data=tensor),
        boxes=[] if fault=='count' else [SimpleNamespace(cls=np.array(0))])
    options={}
    def predict(**kwargs):options.update(kwargs);return [result]
    monkeypatch.setattr(ws,'_load_model',lambda _:SimpleNamespace(predict=predict))
    if fault:
        with pytest.raises(DetectorUnavailable):ws.infer_wall_mask(tmp_path/'source.png',100,40)
    else:
        actual,_=ws.infer_wall_mask(tmp_path/'source.png',100,40)
        assert actual.shape==(40,100)
        assert np.array_equal(actual,mask[0]*255)
    assert options['retina_masks'] is True
