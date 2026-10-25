import numpy as np
from unittest.mock import patch
from PIL import Image
from app.evidence import _segments

def test_hough_returns_n_by_one_by_four():
    arr=np.array([[[0,0,180,0]]],dtype=np.int32)
    with patch('app.evidence.cv2.HoughLinesP',return_value=arr):
        assert len(_segments(Image.new('RGB',(200,100),'white')))==1

def test_hough_returns_n_by_four():
    arr=np.array([[0,0,180,0]],dtype=np.int32)
    with patch('app.evidence.cv2.HoughLinesP',return_value=arr):
        assert len(_segments(Image.new('RGB',(200,100),'white')))==1
