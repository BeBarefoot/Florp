import numpy as np
import pytest
from PIL import Image
from app.yytsi_raster import prepare_raster, restore_mask

def test_png_landscape_is_letterboxed_not_stretched():
    image=Image.new('RGB',(992,440),(255,255,255))
    array,rect=prepare_raster(image,(512,512),True,True)
    assert array.shape==(3,512,512)
    assert rect==(0,142,512,227)
    assert np.isfinite(array).all()
    assert np.max(np.abs(array[:,0,0]))<1e-6  # normalized padding is zero

def test_native_portrait_png_letterbox_has_horizontal_padding():
    arr,rect=prepare_raster(Image.new('RGB',(200,400)),(512,512),True,False)
    assert arr.shape==(3,512,512)
    assert rect==(128,0,256,512)

def test_restore_mask_exact_source_coordinates():
    pred=np.zeros((512,512),dtype=np.uint8)
    pred[142:369,250:270]=1
    pred[:142,:]=3  # padding must not leak into output
    out=restore_mask(pred,(0,142,512,227),(992,440))
    assert out.shape==(440,992)
    assert 3 not in np.unique(out)
    assert out[220,500]==1
    assert out[220,100]==0

def test_non_letterboxed_input_stays_512():
    arr,rect=prepare_raster(Image.new('RGB',(992,440)),(512,512),False,True)
    assert arr.shape==(3,512,512)
    assert rect==(0,0,512,512)

def test_invalid_mask_content_rejected():
    with pytest.raises(ValueError):
        restore_mask(np.zeros((512,512),dtype='uint8'),(0,400,512,200),(992,440))
