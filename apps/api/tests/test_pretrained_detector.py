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
