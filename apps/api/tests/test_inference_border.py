import numpy as np
from app.inference_border import add_inference_border,unpad_probabilities,translate_box

def test_border_preserves_original_and_is_white():
    image=np.zeros((100,200,3),dtype=np.uint8)
    padded,frame=add_inference_border(image,.12,32)
    assert padded.shape==(164,264,3)
    assert padded[0,0].tolist()==[255,255,255]
    assert np.array_equal(padded[32:132,32:232],image)
    assert image.shape==(100,200,3)
    assert (frame.left,frame.top)==(32,32)

def test_map_detections_back_to_original_coordinates():
    img=np.zeros((100,200,3),dtype=np.uint8)
    _,frame=add_inference_border(img,.1,24)
    assert translate_box((34,44,124,94),frame)==(10.,20.,100.,70.)
    assert translate_box((0,0,20,20),frame)==(0.,0.,0.,0.)
    assert translate_box((210,90,300,150),frame)==(186.,66.,200.,100.)

def test_mask_padding_never_survives_crop():
    image=np.zeros((70,130,3),dtype=np.uint8)
    padded,frame=add_inference_border(image,0,12)
    probs=np.full(padded.shape[:2],.8,dtype=np.float32)
    probs[:frame.top,:]=1.
    original=unpad_probabilities(probs,frame)
    assert original.shape==(70,130)
    assert np.allclose(original,.8)

def test_small_legacy_false_area_stays_off_blueprint():
    image=np.zeros((90,180,3),dtype=np.uint8)
    _,frame=add_inference_border(image,.1,20)
    x1,y1,x2,y2=translate_box((2,30,12,70),frame)
    assert x1==x2==0
