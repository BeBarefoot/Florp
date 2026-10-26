import numpy as np
import pytest
from app.multiscale_segmentation import (
    plan_tiles,tile_origins,combine_wall_probabilities
)
from app.mask_topology import region_wall_lines

def test_tiles_cover_image_and_final_edges():
    tiles=plan_tiles(992,440,tile=256,overlap=.25)
    cover=np.zeros((440,992),dtype='uint8')
    for t in tiles:cover[t.y:t.y+t.height,t.x:t.x+t.width]+=1
    assert np.all(cover>=1)
    assert np.max(cover)>1
    assert any(t.x+t.width==992 for t in tiles)

def test_global_and_tile_probs_preserve_source_coordinates():
    image=np.zeros((180,450,3),dtype='uint8')
    image[20:160,300:305,0]=255
    def predict(tile):
        return np.where(tile[:,:,0]>0,1.,0.).astype('float32')
    result,meta=combine_wall_probabilities(image,predict,tile_size=160,overlap=.35)
    assert result.shape==(180,450)
    assert meta['tiles']>1
    assert np.all(result[35:145,301:304]>.99)
    assert not np.any(result[:,50:100]>.01)

def test_no_tile_seam_when_models_agree():
    image=np.full((150,500,3),120,dtype='uint8')
    fused,meta=combine_wall_probabilities(image,
        lambda tile:np.full(tile.shape[:2],.42,dtype='float32'),
        tile_size=192,overlap=.4)
    assert np.allclose(fused,.42,atol=1e-6)

def test_too_many_tiles_guard():
    with pytest.raises(ValueError,match='requires'):
        plan_tiles(5000,5000,tile=256,max_tiles=8)

def test_mask_region_recovers_thin_interior_partition():
    mask=np.zeros((240,420),dtype='uint8')
    mask[35:200,205:209]=255
    mask[100:105,50:360]=255
    report=region_wall_lines(mask,min_length=60)
    assert any(abs(x.x2-x.x1)<=1 and abs(x.y2-x.y1)>130 for x in report.lines)
    assert any(abs(x.y2-x.y1)<=1 and abs(x.x2-x.x1)>250 for x in report.lines)

def test_region_mask_no_fabricated_walls():
    mask=np.zeros((240,420),dtype='uint8')
    assert region_wall_lines(mask).line_count==0
    mask[50:58,50:62]=255
    assert region_wall_lines(mask,min_length=50).line_count==0

def test_region_mask_rejects_overfilled_prediction():
    with pytest.raises(ValueError,match='covers most'):
        region_wall_lines(np.full((120,120),255,dtype='uint8'))
