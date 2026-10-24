"""Inspect locally exported Florp annotation JSON, without uploading it anywhere."""
from __future__ import annotations
import argparse
import collections
import json
from pathlib import Path

VALID={"wall","not_wall","unsure"}

def summarize(document:dict)->dict:
    annotations=document.get('annotations',[])
    if not isinstance(annotations,list):raise ValueError('annotations must be an array')
    counts=collections.Counter()
    coords=set()
    duplicate_count=0
    malformed=0
    for item in annotations:
        if not isinstance(item,dict) or item.get('label') not in VALID:
            malformed+=1
            continue
        try:
            vals=tuple(round(float(item[k]),1) for k in ('x1','y1','x2','y2'))
        except (KeyError,ValueError,TypeError):
            malformed+=1
            continue
        counts[item['label']]+=1
        if vals in coords:duplicate_count+=1
        coords.add(vals)
    manual=document.get('manually_drawn_walls',[])
    return {
       'blueprint_id':document.get('blueprint_id'),
       'dimensions':[document.get('image_width'),document.get('image_height')],
       'labels':dict(counts),
       'manual_wall_count':len(manual),
       'duplicated_segments':duplicate_count,
       'malformed_labels':malformed,
       'ready_to_train':False,
       'notes':[
         'Single-session annotation exports are evaluation data, not trained model weights.',
         'Positive walls and missed-wall annotations are required to evaluate recall.'
       ] if counts['wall']==0 and not manual else [
         'Collect multiple independent blueprints and keep a held-out evaluation split.',
         'Balance positive and negative wall evidence and assess missed walls.'
       ]
    }

def main():
    parser=argparse.ArgumentParser(description='Analyze local Florp wall annotation export')
    parser.add_argument('json_file',type=Path)
    args=parser.parse_args()
    doc=json.loads(args.json_file.read_text(encoding='utf-8'))
    print(json.dumps(summarize(doc),indent=2))

if __name__=='__main__':main()
