"""Raster PNG/JPG/PDF-preview adapter for Yytsi's CubiCasa ResNet34-UNet.

Does not parse SVG; uses buildingcv.PolygonExtractor's already-loaded weights
and applies its exact letterbox/normalization settings to a real raster plan.
The uploaded PDF is rasterized by Florp's normal upload handler first.
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps
from .config import settings
from .pretrained_detector import DetectorUnavailable
from .multiscale_segmentation import combine_wall_probabilities

MEAN=np.array([.485,.456,.406],dtype=np.float32)
STD=np.array([.229,.224,.225],dtype=np.float32)

def prepare_raster(image:Image.Image, size:tuple[int,int], letterbox:bool,
                   normalize:bool) -> tuple[np.ndarray,tuple[int,int,int,int]]:
    """Return CHW float32 tensor values and content rect in model coordinates."""
    original=ImageOps.exif_transpose(image).convert('RGB')
    width,height=original.size
    H,W=size
    if not min(width,height,H,W)>0:raise ValueError('Invalid image or model size')
    if letterbox:
        scale=min(W/width,H/height)
        inner_w=max(1,min(W,int(round(width*scale))))
        inner_h=max(1,min(H,int(round(height*scale))))
    else:inner_w,inner_h=W,H
    resized=original.resize((inner_w,inner_h),Image.Resampling.BILINEAR)
    array=np.asarray(resized,dtype=np.float32)/255.
    if normalize:
        array=(array-MEAN)/STD
        canvas=np.zeros((H,W,3),dtype=np.float32)
    else:
        canvas=np.broadcast_to(MEAN,(H,W,3)).copy()
    left=(W-inner_w)//2;top=(H-inner_h)//2
    canvas[top:top+inner_h,left:left+inner_w]=array
    return np.ascontiguousarray(canvas.transpose(2,0,1)),(left,top,inner_w,inner_h)

def restore_mask(prediction:np.ndarray, rect:tuple[int,int,int,int],
                 target_size:tuple[int,int])->np.ndarray:
    """Crop model padding and nearest-neighbor scale class ids to source pixels."""
    if prediction.ndim!=2:raise ValueError('Expected 2D semantic class mask')
    left,top,width,height=rect
    if width<=0 or height<=0 or left<0 or top<0:
        raise ValueError('Invalid model content bounds')
    if top+height>prediction.shape[0] or left+width>prediction.shape[1]:
        raise ValueError('Model content bounds exceed prediction dimensions')
    cropped=prediction[top:top+height,left:left+width].astype('uint8')
    return np.asarray(Image.fromarray(cropped).resize(target_size,
                     resample=Image.Resampling.NEAREST),dtype=np.uint8)

@lru_cache(maxsize=2)
def _load_extractor(run_directory:str, checkpoint:str, device:str):
    try:
        from buildingcv.extract_polygons import PolygonExtractor
    except ImportError as exc:
        raise DetectorUnavailable('Yytsi dependency missing. Install the optional yytsi extra: uv sync --extra yytsi') from exc
    try:
        return PolygonExtractor(run_dir=Path(run_directory),ckpt=checkpoint,device=device)
    except (OSError,RuntimeError,ValueError,KeyError) as exc:
        raise DetectorUnavailable('Unable to load Yytsi checkpoint/config: '+str(exc)[:240]) from exc

def _predict_wall_probability(extractor,rgb:np.ndarray,wall_class:int)->np.ndarray:
    import cv2
    import torch
    image=Image.fromarray(rgb,'RGB')
    tensor,rect=prepare_raster(image,extractor.image_size,
                                  extractor.letterbox,extractor.normalize)
    input_tensor=torch.from_numpy(tensor).unsqueeze(0).to(extractor.device)
    with torch.inference_mode():
        scores=extractor.model(input_tensor)
        # Float probabilities, not argmax: local tiles can reinforce fine walls.
        probability=torch.softmax(scores.float(),dim=1)[0,wall_class].cpu().numpy()
    x,y,w,h=rect
    crop=probability[y:y+h,x:x+w]
    return cv2.resize(crop,(rgb.shape[1],rgb.shape[0]),
                      interpolation=cv2.INTER_LINEAR).astype('float32')


def predict_yytsi_raster(preview:Path,width:int,height:int)->tuple[np.ndarray,dict]:
    run_dir=Path(settings.yytsi_run_dir).expanduser().resolve()
    if not (run_dir/'config.yaml').is_file() or not (run_dir/settings.yytsi_checkpoint).is_file():
        raise DetectorUnavailable('Yytsi requires config.yaml and '+settings.yytsi_checkpoint+
            ' in YYTSI_RUN_DIR.')
    extractor=_load_extractor(str(run_dir),settings.yytsi_checkpoint,settings.yytsi_device)
    try:
        from buildingcv.labels import CLASS_TO_ID
        with Image.open(preview) as image:
            original=ImageOps.exif_transpose(image).convert('RGB')
            if original.size!=(width,height):
                raise ValueError('Preview dimensions do not match stored blueprint')
            rgb=np.asarray(original,dtype=np.uint8)
        wall_id=CLASS_TO_ID['wall']
        def predict(tile):
            return _predict_wall_probability(extractor,tile,wall_id)
        if settings.segmentation_multiscale:
            probabilities,stats=combine_wall_probabilities(rgb,predict,
                tile_size=settings.segmentation_tile_size,
                overlap=settings.segmentation_tile_overlap,
                max_tiles=settings.segmentation_max_tiles)
        else:
            probabilities=predict(rgb)
            stats={'tiles':0,'method':'global_only','source_resolution':[width,height]}
        threshold=settings.segmentation_wall_threshold
        wall=np.where(probabilities>=threshold,255,0).astype(np.uint8)
        return wall,{'provider':'Yytsi/ResNet34-UNet','checkpoint':settings.yytsi_checkpoint,
            'input_format':'raster_png','image_size':[width,height],
            'wall_fraction':round(float(np.mean(wall>0)),5),
            'wall_threshold':threshold,'multiscale':stats,
            'warning':'Tiled predictions are model hypotheses; verify interior walls, furniture and annotations.'}
    except DetectorUnavailable:raise
    except (RuntimeError,ValueError,OSError,MemoryError) as exc:
        raise DetectorUnavailable('Yytsi multi-scale inference failed: '+str(exc)[:260]) from exc
