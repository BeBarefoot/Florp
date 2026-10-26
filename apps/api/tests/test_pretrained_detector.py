from types import SimpleNamespace
from app.pretrained_detector import normalize_yolo_boxes, DetectionBox

class Scalar:
    def __init__(self,v):self.v=v
    def item(self):return self.v
class Coords:
    def __init__(self,values):self.values=values
    def tolist(self):return self.values

def test_yolo_model_boxes_are_normalized_and_clipped():
    result=SimpleNamespace(names={0:'Wall',1:'Door'},boxes=[
        SimpleNamespace(conf=Scalar(.9),cls=Scalar(0),xyxy=[Coords([-3,10,80,120])]),
        SimpleNamespace(conf=Scalar(.1),cls=Scalar(1),xyxy=[Coords([10,10,20,20])])
    ])
    boxes=normalize_yolo_boxes([result],100,100,threshold=.35)
    assert len(boxes)==1
    assert boxes[0].category=='wall'
    assert boxes[0].x1==0 and boxes[0].y2==100

def test_zero_area_boxes_rejected():
    result=SimpleNamespace(names={0:'wall'},boxes=[
        SimpleNamespace(conf=Scalar(.9),cls=Scalar(0),xyxy=[Coords([50,10,50,20])])])
    assert normalize_yolo_boxes([result],100,100)==[]

def test_detect_objects_with_padding_no_name_error_and_original_coordinates(tmp_path,monkeypatch):
    from PIL import Image
    from app import pretrained_detector as detector
    image=tmp_path/'preview.png'
    Image.new('RGB',(200,100),'white').save(image)
    class FakeModel:
        def predict(self,source,**kwargs):
            assert source.shape==(164,264,3)
            return [SimpleNamespace(names={0:'wall'},boxes=[
                SimpleNamespace(conf=Scalar(.95),cls=Scalar(0),
                    xyxy=[Coords([42,52,162,62])])])]
    monkeypatch.setattr(detector,'_load_model',lambda weights:FakeModel())
    monkeypatch.setattr(detector.settings,'pretrained_yolo_weights',str(image))
    monkeypatch.setattr(detector.settings,'inference_border_enabled',True)
    monkeypatch.setattr(detector.settings,'inference_border_fraction',.12)
    monkeypatch.setattr(detector.settings,'inference_border_min_px',32)
    result=detector.detect_objects(image,200,100)
    assert (result.image_width,result.image_height)==(200,100)
    assert len(result.boxes)==1
    box=result.boxes[0]
    assert (box.x1,box.y1,box.x2,box.y2)==(10.,20.,130.,30.)
