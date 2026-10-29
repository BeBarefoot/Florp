"""Evaluate an independently reviewed, held-out end-to-end release corpus."""
import argparse,json,hashlib,math
from pathlib import Path
from app.extraction_benchmark import load_prediction,image_identity,compare

def evaluate(manifest_path:Path)->dict:
    doc=json.loads(manifest_path.read_text());cases=doc['cases'];root=manifest_path.resolve().parent
    if doc.get('split')!='test' or doc.get('frozen') is not True:raise ValueError('Require a frozen held-out test corpus')
    groups=set();images=set();reports=[]
    for c in cases:
        if c.get('independently_reviewed') is not True:raise ValueError('Reference is not independently reviewed')
        identity=image_identity(root/c['image']);sha=identity['image_sha256']
        if sha in images:raise ValueError('Duplicate image in release corpus')
        images.add(sha);groups.add(c['group_id'])
        truth=load_prediction(root/c['truth']);prediction=load_prediction(root/c['prediction'])
        for record in (truth,prediction):
            if (record.image_sha256,record.width_px,record.height_px)!=(sha,identity['width_px'],identity['height_px']):
                raise ValueError('Prediction/reference is not bound to original image')
        seconds=c.get('correction_seconds')
        if not isinstance(seconds,(int,float)) or isinstance(seconds,bool) or not math.isfinite(seconds) or seconds<0:
            raise ValueError('Measured finite nonnegative correction_seconds required')
        metrics=compare(truth,prediction,tolerance_px=3.)
        length=metrics['wall_length_coverage'];opening=metrics['opening_spans']
        from app.geometry import Geometry,Wall,Pt
        from app.graph_adapter import from_geometry
        from app.topology_metrics import TopologyCase,compare_topology
        def case(record,gold):
            geometry=Geometry(width_px=record.width_px,height_px=record.height_px,walls=[Wall(id=f'edge-{i}',start=Pt(x=w.start.x,y=w.start.y),end=Pt(x=w.end.x,y=w.end.y)) for i,w in enumerate(record.walls)])
            return TopologyCase(source_preview_sha256=sha,provider=record.provider,gold_standard=gold,plan=from_geometry(geometry))
        topology=compare_topology(case(truth,True),case(prediction,False),tolerance_px=3.)
        if not truth.walls:raise ValueError('Empty reference geometry is not a release case')
        passed=(topology['junctions']['f1']>=.95 and topology['wall_adjacency_edges']['f1']>=.95
                and topology['room_regions_at_iou_0_5']['f1']>=.9 and topology['reference_health']['supported_room_cycles']>0
                and length['precision']>=.9 and length['recall']>=.9 and opening['precision']>=.95 and opening['recall']>=.95
                and c.get('exterior_complete') is True and c.get('opening_spans_reviewed') is True)
        reports.append({'source_sha256':sha,'group_id':c['group_id'],'metrics':metrics,'topology':topology,'passed':passed,
                        'correction_seconds':seconds})
    fast=sum(r['correction_seconds']<=300 for r in reports)/len(reports) if reports else 0.
    passed=len(reports)>=10 and len(groups)>=10 and all(r['passed'] for r in reports) and fast>=.8
    return {'passed':passed,'case_count':len(reports),'independent_groups':len(groups),
            'within_5_minutes_fraction':fast,'cases':reports,
            'manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            'scope':'Geometry acceptance only; not authorization, load, operational or deployment approval'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();report=evaluate(a.manifest);a.output.write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='cases'}))
    raise SystemExit(0 if report['passed'] else 2)
if __name__=='__main__':main()
