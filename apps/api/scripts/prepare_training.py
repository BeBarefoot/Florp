"""Build source-bound train/val/test polygon-mask datasets without guessing labels."""
import argparse,json
from pathlib import Path
from app.training_dataset import prepare,Annotation,Manifest

def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path);p.add_argument('--output',type=Path)
    p.add_argument('--schema',choices=['annotation','manifest']);a=p.parse_args()
    if a.schema:
        print(json.dumps((Annotation if a.schema=='annotation' else Manifest).model_json_schema(),indent=2));return
    if not a.manifest or not a.output:p.error('--manifest and --output are required')
    report=prepare(a.manifest,a.output)
    print(json.dumps({'cases':len(report['cases']),'output':str(a.output),'manifest_sha256':report['manifest_sha256']}))
if __name__=='__main__':main()
