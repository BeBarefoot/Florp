"""Multi-scale wall probability fusion in original blueprint coordinates.

Global context + overlapping tiles; blend softmax probabilities with feathered
weights. No inference takes place at import; a predict callback is injectable
for deterministic tests. The returned mask never implies verified geometry.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import ceil
import numpy as np
import cv2

@dataclass(frozen=True)
class Tile:
    x:int
    y:int
    width:int
    height:int

def tile_origins(length:int, tile:int, overlap:float)->list[int]:
    if length<1 or tile<1 or not 0<=overlap<.75:
        raise ValueError('Invalid tile shape or overlap')
    if length<=tile:return [0]
    stride=max(1,int(round(tile*(1-overlap))))
    positions=list(range(0,length-tile+1,stride))
    if positions[-1]!=length-tile:positions.append(length-tile)
    return positions

def plan_tiles(width:int,height:int, tile:int=448,overlap:float=.30,
               max_tiles:int=64)->list[Tile]:
    if width<1 or height<1:raise ValueError('Invalid raster size')
    xs=tile_origins(width,tile,overlap)
    ys=tile_origins(height,tile,overlap)
    if len(xs)*len(ys)>max_tiles:
        raise ValueError(f'Multi-scale grid requires {len(xs)*len(ys)} tiles; increase tile size or limit image resolution')
    return [Tile(x,y,min(tile,width-x),min(tile,height-y)) for y in ys for x in xs]

def feather_weights(h:int,w:int)->np.ndarray:
    # Positive everywhere so isolated boundary pixels are never divided by zero.
    x=np.minimum(np.arange(w)+1,np.arange(w,0,-1)).astype('float32')
    y=np.minimum(np.arange(h)+1,np.arange(h,0,-1)).astype('float32')
    x=np.clip(x/max(1,min(w//7,36)),.2,1)
    y=np.clip(y/max(1,min(h//7,36)),.2,1)
    return y[:,None]*x[None,:]

def combine_wall_probabilities(image:np.ndarray,predict, tile_size:int=448,
                  overlap:float=.30, global_weight:float=.65,
                  max_tiles:int=64)->tuple[np.ndarray,dict]:
    """predict(rgb uint8 array)->wall float32 probability in tile source dimensions."""
    if image.ndim!=3 or image.shape[2]!=3 or image.dtype!=np.uint8:
        raise ValueError('Expected H×W×3 RGB uint8 input')
    h,w=image.shape[:2]
    tiles=plan_tiles(w,h,tile_size,overlap,max_tiles)
    base=np.asarray(predict(image),dtype='float32')
    if base.shape!=(h,w) or not np.isfinite(base).all():
        raise ValueError('Global prediction shape/values invalid')
    if not (0<=base).all() or not (base<=1).all():
        raise ValueError('Global predictions must be wall probabilities in [0,1]')
    total=np.maximum(global_weight,0)*base
    weights=np.full((h,w),max(global_weight,0),dtype='float32')
    for tile in tiles:
        chip=image[tile.y:tile.y+tile.height,tile.x:tile.x+tile.width]
        p=np.asarray(predict(chip),dtype='float32')
        if p.shape!=(tile.height,tile.width) or not np.isfinite(p).all():
            raise ValueError('Tile prediction shape/values invalid')
        if np.any((p<0)|(p>1)):raise ValueError('Tile probabilities outside [0,1]')
        taper=feather_weights(tile.height,tile.width)
        sl=np.s_[tile.y:tile.y+tile.height,tile.x:tile.x+tile.width]
        total[sl]+=p*taper
        weights[sl]+=taper
    result=total/np.maximum(weights,1e-7)
    return result,{'tiles':len(tiles),'tile_size':tile_size,'overlap':overlap,
                   'global_weight':global_weight,'source_resolution':[w,h],
                   'method':'feathered_global_tile_probability_fusion'}
