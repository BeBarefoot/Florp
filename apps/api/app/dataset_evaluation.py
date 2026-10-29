"""Frozen validation comparison against reviewed masks, never the held-out test set."""
import json,zipfile
from pathlib import Path
from shapely.geometry import Polygon
from shapely.ops import unary_union
from .training_dataset import verify_dataset,digest
from .annotation_geometry import reconstruct

def footprint_metrics(truth,prediction):
    result={}
    for kind in ('wall','door','window'):
        def union(items):return unary_union([Polygon(o['polygon']) for o in items if o['kind']==kind])
        gold=union(truth);pred=union(prediction);intersection=gold.intersection(pred).area
        result[kind]={'iou':intersection/gold.union(pred).area if gold.union(pred).area else 1.,'precision':intersection/pred.area if pred.area else (1. if not gold.area else 0.),'recall':intersection/gold.area if gold.area else (1. if not pred.area else 0.)}
    return result

def compare_checkpoints(dataset:Path,baseline:Path,candidate:Path,output:Path,device='cpu'):
    from ultralytics import YOLO
    from .extraction_exports import normalize_florp_geometry
    from .extraction_benchmark import compare
    report=verify_dataset(dataset);models={'baseline':YOLO(str(baseline)),'candidate':YOLO(str(candidate))}
    output.mkdir(parents=True,exist_ok=False);cases=[]
    with zipfile.ZipFile(dataset/'source-annotations.zip') as archive:
        for case in report['cases']:
            if case['split']!='val':continue
            image=dataset/case['prepared_image'];ann=json.loads(archive.read('cases/'+case['id']+'/annotation.json'))
            truth=ann['objects'];w,h=ann['width_px'],ann['height_px'];gold_geometry=reconstruct(truth,w,h,ann.get('px_per_meter'))['geometry']
            record={'id':case['id'],'group_id':case['group_id'],'models':{}}
            for name,model in models.items():
                result=model.predict(source=str(image),imgsz=1024,conf=.25,retina_masks=True,device=device,verbose=False)[0]
                if tuple(result.orig_shape)!=(h,w):raise ValueError('Prediction source coordinate mismatch')
                objects=[]
                if result.masks is not None:
                    for polygon,box in zip(result.masks.xy,result.boxes):
                        label=str(result.names[int(box.cls.item())]).lower().rstrip('s')
                        if label not in ('wall','door','window'):continue
                        points=polygon.tolist()
                        if len(points)<3:continue
                        poly=Polygon(points)
                        if not poly.is_valid or poly.area<1:continue
                        if any(not(0<=x<=w and 0<=y<=h) for x,y in points):raise ValueError('Prediction outside source coordinates')
                        objects.append({'kind':label,'polygon':points})
                geometry=reconstruct(objects,w,h,ann.get('px_per_meter'))['geometry']
                metrics={'footprints':footprint_metrics(truth,objects),'derived_geometry':compare(normalize_florp_geometry(image,gold_geometry),normalize_florp_geometry(image,geometry))}
                raw={'objects':objects,'geometry':geometry,'metrics':metrics}
                (output/(case['id']+'-'+name+'.json')).write_text(json.dumps(raw,indent=2))
                record['models'][name]=metrics
            cases.append(record)
    result={'split':'val','dataset_sha256':digest(dataset/'provenance.json'),'baseline_sha256':digest(baseline),'candidate_sha256':digest(candidate),'cases':cases,'production_approved':False,'note':'Geometry references are derived from reviewed masks. Independent structural/scale and frozen test acceptance remain separate.'}
    (output/'report.json').write_text(json.dumps(result,indent=2));return result
