"""Adapters into the strict benchmark schema.

For Tectly/Raster2Seq, import only an explicitly normalized export. Vendor
response contracts and coordinate units must be verified before a native
adapter is allowed; no blind inference or fabricated scores.
"""
from __future__ import annotations
from pathlib import Path
import argparse
import json
from .extraction_benchmark import PlanPrediction,Point,Segment,OpeningLabel,image_identity,save_prediction

def normalize_florp_geometry(image:Path, geometry:dict,
                              provider:str='florp-saved-layout')->PlanPrediction:
    from .geometry import Geometry
    g=Geometry.model_validate(geometry)
    identity=image_identity(image)
    if (g.width_px,g.height_px)!=(identity['width_px'],identity['height_px']):
        raise ValueError('Florp layout dimensions do not match the original preview')
    def pt(p):return Point(x=p.x,y=p.y)
    walls=[Segment(start=pt(w.start),end=pt(w.end)) for w in g.walls]
    rooms=[[pt(p) for p in room.points] for room in g.rooms]
    openings=[]
    for o in g.openings:
        wall=next((wall for wall in g.walls if wall.id==o.wall_id),None)
        if wall is None:continue
        px_per_meter=g.px_per_meter
        if px_per_meter is None or g.scale_source!='user_confirmed':
            # A provisional/unknown metric scale cannot provide reliable
            # source-pixel opening spans for accuracy scoring.
            continue
        dx=wall.end.x-wall.start.x
        dy=wall.end.y-wall.start.y
        length=(dx*dx+dy*dy)**.5
        if length==0:continue
        start=o.offset_m*px_per_meter/length
        end=(o.offset_m+o.width_m)*px_per_meter/length
        if not (0<=start<end<=1):continue
        openings.append(OpeningLabel(kind=o.kind,
            start=Point(x=wall.start.x+start*dx,y=wall.start.y+start*dy),
            end=Point(x=wall.start.x+end*dx,y=wall.start.y+end*dy)))
    return PlanPrediction(provider=provider,**identity,
        walls=walls,rooms=rooms,openings=openings,
        px_per_meter=g.px_per_meter,scale_source=g.scale_source,
        metadata={'geometry_reviewed':g.structure_reviewed,
                  'note':'Provisional openings without confirmed metric scale are excluded'})

def normalize_yolo(image:Path)->PlanPrediction:
    from .pretrained_detector import detect_objects
    from .model_reconstruction import _model_wall_candidates
    identity=image_identity(image)
    detector=detect_objects(image,identity['width_px'],identity['height_px'])
    candidates,_=_model_wall_candidates(detector)
    walls=[Segment(start=Point(x=a.x,y=a.y),end=Point(x=b.x,y=b.y))
           for _,a,b in candidates]
    return PlanPrediction(provider='florp-yolo',**identity,walls=walls,
        metadata={'detections':len(detector.boxes),
                  'opening_boxes_not_geometry':sum(b.category in ('door','window') for b in detector.boxes)})

def normalize_yytsi(image:Path)->PlanPrediction:
    from .yytsi_raster import predict_yytsi_raster
    from .mask_topology import region_wall_lines
    from .wall_run_normalization import consolidate_wall_runs
    identity=image_identity(image)
    w,h=identity['width_px'],identity['height_px']
    mask,metadata=predict_yytsi_raster(image,w,h)
    report=consolidate_wall_runs(region_wall_lines(mask,min_length=max(22,min(w,h)//18)))
    return PlanPrediction(provider='florp-yytsi',**identity,
        walls=[Segment(start=Point(x=l.x1,y=l.y1),end=Point(x=l.x2,y=l.y2))
               for l in report.lines],metadata=metadata)

def import_normalized(image:Path,source:Path,provider:str)->PlanPrediction:
    """Third-party exports must explicitly use schema_version=1 and original pixels."""
    identity=image_identity(image)
    data=json.loads(source.read_text(encoding='utf-8'))
    if not isinstance(data,dict):raise ValueError('Expected a JSON object')
    if data.get('schema_version')!=1:
        raise ValueError('Third-party JSON not normalized; convert with verified provider mapping first')
    if data.get('provider')!=provider:
        raise ValueError('Provider name mismatch')
    prediction=PlanPrediction.model_validate(data)
    if any(getattr(prediction,k)!=v for k,v in identity.items()):
        raise ValueError('Third-party export has different image identity or coordinates')
    return prediction

def main():
    parser=argparse.ArgumentParser(description='Export candidate geometry for independent benchmarking')
    parser.add_argument('--image',type=Path,required=True)
    parser.add_argument('--provider',required=True,choices=['florp-layout','florp-yolo','florp-yytsi','normalized-external'])
    parser.add_argument('--source',type=Path,help='Florp Geometry JSON or explicitly normalized external JSON')
    parser.add_argument('--external-name',help='Exact external provider identifier')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.provider=='florp-layout':
        if not args.source:parser.error('--source is required')
        result=normalize_florp_geometry(args.image,json.loads(args.source.read_text()))
    elif args.provider=='florp-yolo':
        result=normalize_yolo(args.image)
    elif args.provider=='florp-yytsi':
        result=normalize_yytsi(args.image)
    else:
        if not args.source or not args.external_name:parser.error('--source and --external-name required')
        result=import_normalized(args.image,args.source,args.external_name)
    save_prediction(args.output,result)
    print(f'Saved {result.provider}: {len(result.walls)} walls, {len(result.rooms)} rooms, {len(result.openings)} openings')

if __name__=='__main__':main()
