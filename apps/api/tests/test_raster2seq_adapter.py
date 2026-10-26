import pytest
from fastapi import HTTPException
from app.raster2seq_adapter import (
    canvas_mapping, decode_rooms, Raster2SeqUnavailable, run_raster2seq,
)

def test_canvas_mapping_matches_upstream_center_padding():
    scale,left,top=canvas_mapping(992,440,256)
    assert scale==256/992
    assert left==0
    assert top==(256-int(440*scale))//2

def test_inverse_mapping_returns_original_polygon():
    width,height=992,440
    scale,left,top=canvas_mapping(width,height,256)
    original=[(120,60),(480,60),(480,200),(120,200)]
    coords=[[x*scale+left,y*scale+top] for x,y in original]
    output=decode_rooms([{'image_id':'plan','segmentation':coords,'category_id':3,'id':0}],
        width,height)
    assert len(output)==1
    assert output[0].category_id==3
    for pair,actual in zip(original,output[0].points):
        assert actual==pytest.approx(pair,abs=.005)

def test_flat_polygon_accepted_and_closed_point_removed():
    raw=[{'segmentation':[30,30,200,30,200,180,30,30],'category_id':2}]
    rooms=decode_rooms(raw,256,256)
    assert len(rooms)==1
    assert len(rooms[0].points)==3

def test_empty_and_bad_polygon_handling():
    assert decode_rooms([],400,200)==[]
    with pytest.raises(ValueError,match='JSON must'):
        decode_rooms({'room':[]},400,200)
    with pytest.raises(ValueError,match='Odd-length'):
        decode_rooms([{'segmentation':[1,2,3],'category_id':1}],256,256)
    with pytest.raises(ValueError,match='Nonfinite'):
        decode_rooms([{'segmentation':[[1,1],[float('nan'),3],[3,3]],'category_id':1}],256,256)

def test_missing_runtime_is_explicit(tmp_path):
    with pytest.raises(Raster2SeqUnavailable,match='RASTER2SEQ_ROOT'):
        run_raster2seq(tmp_path/'missing.png',root=tmp_path/'no-checkout',
            python_exec=tmp_path/'no-python')

def test_raster2seq_disabled_returns_424(monkeypatch):
    from app import main
    monkeypatch.setattr(main.settings,'raster2seq_enabled',False)
    with pytest.raises(HTTPException) as error:
        main.compare_raster2seq('missing-blueprint')
    assert error.value.status_code==424
