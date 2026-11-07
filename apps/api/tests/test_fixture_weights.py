from types import SimpleNamespace
import numpy as np
import pytest
from app import fixture_weights

class Tensor:
    def __init__(self, rows): self.rows = rows
    def cpu(self): return self
    def tolist(self): return self.rows

def test_weight_boxes_use_original_coordinates_and_metric_size(tmp_path, monkeypatch):
    path = tmp_path / 'trusted.pt'
    path.write_bytes(b'mocked checkpoint')
    boxes = SimpleNamespace(xyxy=Tensor([[100, 100, 200, 300], [0, 0, 10, 10], [-1, 0, 20, 20]]),
                            conf=Tensor([.8, .9, .9]), cls=Tensor([0, 1, 0]))
    result = SimpleNamespace(boxes=boxes, names={0:'bed', 1:'wall'})
    def predict(**kwargs):
        assert kwargs['source'].shape == (600, 800, 3)
        assert kwargs['device'] == 'cpu'
        return [result]
    monkeypatch.setattr(fixture_weights, 'load', lambda *args: SimpleNamespace(predict=predict))
    hit, = fixture_weights.detect(np.zeros((600,800),np.uint8), .01, str(path))
    assert (hit.kind, hit.x, hit.y, hit.width, hit.depth) == ('bed',150,200,1,2)

def test_missing_weights_do_not_trigger_download(tmp_path):
    with pytest.raises(ValueError, match='trusted local'):
        fixture_weights.detect(np.zeros((20,20),np.uint8), .01, str(tmp_path/'missing.pt'))
