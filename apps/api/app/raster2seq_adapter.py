"""Raster2Seq experimental adapter: isolated subprocess + exact inverse resize/pad.

Official upstream: Cornell-VAILab/Raster2Seq, predict.py --save_pred.
Source code MIT; official checkpoint CC BY-NC 4.0: evaluation only,
not approved for commercial production without separate permission.
"""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
from PIL import Image
from pydantic import BaseModel,Field

class Raster2SeqUnavailable(RuntimeError):pass
class R2SRoom(BaseModel):
    category_id:int
    points:list[tuple[float,float]]=Field(min_length=3)

def canvas_mapping(width:int,height:int,canvas:int=256)->tuple[float,int,int]:
    if min(width,height,canvas)<=0:raise ValueError('Invalid image dimensions')
    scale=min(canvas/height,canvas/width)
    # Reproduce upstream ResizeAndPad: integer truncation, centered padding.
    resized_w=int(width*scale)
    resized_h=int(height*scale)
    if min(resized_w,resized_h)<1:raise ValueError('Input too extreme for Raster2Seq canvas')
    return scale,(canvas-resized_w)//2,(canvas-resized_h)//2

def decode_rooms(raw:list, width:int,height:int, canvas:int=256)->list[R2SRoom]:
    if not isinstance(raw,list):raise ValueError('Raster2Seq JSON must be a list')
    scale,pad_x,pad_y=canvas_mapping(width,height,canvas)
    rooms=[]
    for item in raw:
        if not isinstance(item,dict) or 'segmentation' not in item or 'category_id' not in item:
            raise ValueError('Unexpected Raster2Seq prediction entry')
        poly=item['segmentation']
        # Upstream save_pred uses poly.astype(float).tolist(); accept Nx2 or flat 2N.
        if not isinstance(poly,list):raise ValueError('Invalid polygon')
        if poly and isinstance(poly[0],(int,float)):
            if len(poly)%2:raise ValueError('Odd-length flat polygon')
            pairs=list(zip(poly[::2],poly[1::2]))
        else:pairs=poly
        if len(pairs)<3:continue
        points=[]
        for xy in pairs:
            if not isinstance(xy,(list,tuple)) or len(xy)!=2:raise ValueError('Invalid polygon coordinate')
            x,y=xy
            if not isinstance(x,(int,float)) or not isinstance(y,(int,float)) or not math.isfinite(x) or not math.isfinite(y):
                raise ValueError('Nonfinite polygon coordinate')
            # Predicted coordinates lie in model canvas, including upstream
            # centered whitespace, and are mapped back to ORIGINAL pixels.
            px=max(0.,min(float(width),(float(x)-pad_x)/scale))
            py=max(0.,min(float(height),(float(y)-pad_y)/scale))
            if not points or math.hypot(px-points[-1][0],py-points[-1][1])>.5:
                points.append((round(px,3),round(py,3)))
        if len(points)>2 and math.dist(points[0],points[-1])<=.5:points.pop()
        if len(points)<3:continue
        from shapely.geometry import Polygon
        polygon=Polygon(points)
        if not polygon.is_valid or polygon.area<4:continue
        rooms.append(R2SRoom(category_id=int(item['category_id']),points=points))
    return rooms

def run_raster2seq(image_path:Path, *, root:Path,python_exec:Path,
                   device:str='cuda',checkpoint:str='hf:cubicasa5k',
                   timeout_seconds:int=600, canvas:int=256)->tuple[list[R2SRoom],dict]:
    root=root.expanduser().resolve()
    python_exec=python_exec.expanduser()
    if not root.is_dir() or not (root/'predict.py').is_file():
        raise Raster2SeqUnavailable('RASTER2SEQ_ROOT must point to a checkout containing predict.py')
    if not python_exec.is_file():
        raise Raster2SeqUnavailable('RASTER2SEQ_PYTHON must point to the isolated Python environment')
    if device not in ('cuda','cpu'):raise ValueError('Unsupported device')
    if not checkpoint.startswith('hf:') and not Path(checkpoint).is_file():
        raise Raster2SeqUnavailable('Checkpoint path not found')
    with Image.open(image_path) as image:
        width,height=image.size
        rgb=image.convert('RGB')
        with tempfile.TemporaryDirectory(prefix='florp-r2s-') as workspace:
            tmp=Path(workspace);input_dir=tmp/'input';input_dir.mkdir()
            # Unique filename: never modify saved blueprints or allow
            # concurrent requests to overwrite each other's outputs.
            rgb.save(input_dir/'plan.png')
            out=tmp/'output'
            cmd=[str(python_exec),str(root/'predict.py'),
                 '--dataset_name=cubicasa','--dataset_root',str(input_dir),
                 '--checkpoint',checkpoint,'--output_dir',str(out),
                 '--semantic_classes=12','--input_channels','3',
                 '--poly2seq','--seq_len','512','--num_bins','32',
                 '--disable_poly_refine','--dec_attn_concat_src',
                 '--per_token_sem_loss','--use_anchor','--ema4eval',
                 '--image_size',str(canvas),'--batch_size','1',
                 '--num_workers','0','--device',device,'--save_pred']
            try:
                completed=subprocess.run(cmd,cwd=root,capture_output=True,text=True,
                    timeout=timeout_seconds,check=False,env=os.environ.copy())
            except subprocess.TimeoutExpired as exc:
                raise Raster2SeqUnavailable('Inference exceeded configured timeout') from exc
            except OSError as exc:raise Raster2SeqUnavailable('Unable to launch Raster2Seq') from exc
            if completed.returncode:
                # Keep diagnostic bounded; don't expose environment variables.
                raise Raster2SeqUnavailable(
                    f'Raster2Seq exited {completed.returncode}: '+completed.stderr[-700:])
            matches=list(out.glob('**/jsons/plan.json'))
            if len(matches)!=1:
                raise Raster2SeqUnavailable('Expected one Raster2Seq saved prediction JSON')
            try:raw=json.loads(matches[0].read_text(encoding='utf-8'))
            except (ValueError,OSError) as exc:
                raise Raster2SeqUnavailable('Invalid Raster2Seq output JSON') from exc
            rooms=decode_rooms(raw,width,height,canvas)
            return rooms,{'provider':'raster2seq','checkpoint':checkpoint,
                          'canvas_size':canvas,'device':device,
                          'predicted_rooms':len(rooms),
                          'experimental':True,'verified_geometry':False}
