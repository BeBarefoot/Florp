"""Validated, source-bound segmentation datasets. Draft labels are not gold masks."""
from __future__ import annotations
import hashlib,json,shutil,tempfile
from pathlib import Path
from typing import Literal
from PIL import Image
from pydantic import BaseModel,ConfigDict,Field,model_validator
from shapely.geometry import Polygon

CLASSES={'wall':0,'door':1,'window':2}
class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',allow_inf_nan=False)
class ObjectMask(Strict):
    kind:Literal['wall','door','window']
    polygon:list[tuple[float,float]]=Field(min_length=3)
class Annotation(Strict):
    schema_version:Literal[1]=1
    width_px:int=Field(gt=0)
    height_px:int=Field(gt=0)
    independently_reviewed:Literal[True]
    annotation_complete:Literal[True]
    reviewer:str=Field(min_length=1)
    objects:list[ObjectMask]=Field(min_length=1)
    @model_validator(mode='after')
    def valid_masks(self):
        for item in self.objects:
            if any(not(0<=x<=self.width_px and 0<=y<=self.height_px) for x,y in item.polygon):
                raise ValueError('Polygon outside original image')
            poly=Polygon(item.polygon)
            if not poly.is_valid or poly.area<1:raise ValueError('Invalid/degenerate mask polygon')
        if not any(o.kind=='wall' for o in self.objects):raise ValueError('No wall masks')
        return self
class Case(Strict):
    id:str=Field(pattern=r'^[a-zA-Z0-9_-]+$')
    group_id:str=Field(min_length=1)
    split:Literal['train','val','test']
    image:str
    annotation:str
    source_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    usage_rights_confirmed:Literal[True]
class Manifest(Strict):
    schema_version:Literal[1]=1
    cases:list[Case]=Field(min_length=3)

def digest(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()

def prepare(manifest_path:Path,output:Path)->dict:
    manifest=Manifest.model_validate_json(manifest_path.read_text())
    if output.exists():raise ValueError('Output already exists; create a new immutable dataset version')
    root=manifest_path.resolve().parent
    ids=set();groups={};sources={};pixels={};validated=[]
    for c in manifest.cases:
        if c.id in ids:raise ValueError('Duplicate case ID')
        ids.add(c.id)
        if c.group_id in groups and groups[c.group_id]!=c.split:raise ValueError('Building/group leakage between splits')
        groups[c.group_id]=c.split
        image_path=(root/c.image).resolve();annotation_path=(root/c.annotation).resolve()
        if digest(image_path)!=c.source_sha256:raise ValueError('Source SHA256 mismatch')
        if c.source_sha256 in sources:raise ValueError('Duplicate source image')
        sources[c.source_sha256]=c.id
        ann=Annotation.model_validate_json(annotation_path.read_text())
        with Image.open(image_path) as im:
            if im.getexif().get(274,1)!=1:raise ValueError('Normalize image orientation before annotation')
            if im.size!=(ann.width_px,ann.height_px):raise ValueError('Annotation/image dimensions differ')
            rgb=im.convert('RGB')
            pixel_hash=hashlib.sha256(str(rgb.size).encode()+rgb.tobytes()).hexdigest()
        if pixel_hash in pixels:raise ValueError('Duplicate decoded image, possibly re-encoded leakage')
        pixels[pixel_hash]=c.id
        lines=[]
        for obj in ann.objects:
            coords=' '.join(f'{v:.9f}' for x,y in obj.polygon for v in (x/ann.width_px,y/ann.height_px))
            lines.append(f'{CLASSES[obj.kind]} {coords}')
        validated.append((c,ann,rgb,'\n'.join(lines)+'\n',digest(annotation_path)))
    if {c.split for c in manifest.cases}!={'train','val','test'}:raise ValueError('Train, validation and held-out test splits are required')
    output=output.resolve();output.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix='.dataset-',dir=output.parent))
    try:
        records=[]
        for c,ann,rgb,labels,ann_hash in validated:
            ip=stage/'images'/c.split/(c.id+'.png');lp=stage/'labels'/c.split/(c.id+'.txt')
            ip.parent.mkdir(parents=True,exist_ok=True);lp.parent.mkdir(parents=True,exist_ok=True)
            rgb.save(ip);lp.write_text(labels)
            records.append({**c.model_dump(),'annotation_sha256':ann_hash,
                'prepared_image':str(ip.relative_to(stage)),'prepared_image_sha256':digest(ip),
                'prepared_label':str(lp.relative_to(stage)),'prepared_label_sha256':digest(lp),
                'reviewer':ann.reviewer})
        yaml='path: '+json.dumps(str(output))+'\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n  0: wall\n  1: door\n  2: window\n'
        (stage/'dataset.yaml').write_text(yaml)
        report={'schema_version':1,'manifest_sha256':digest(manifest_path),
                'classes':CLASSES,'dataset_yaml_sha256':digest(stage/'dataset.yaml'),'cases':records}
        (stage/'provenance.json').write_text(json.dumps(report,indent=2))
        stage.rename(output)
    except BaseException:
        shutil.rmtree(stage,ignore_errors=True);raise
    return report

def verify_dataset(path:Path)->dict:
    report=json.loads((path/'provenance.json').read_text())
    if digest(path/'dataset.yaml')!=report['dataset_yaml_sha256']:raise ValueError('Dataset YAML changed after preparation')
    for c in report['cases']:
        for field in ('prepared_image','prepared_label'):
            if digest(path/c[field])!=c[field+'_sha256']:raise ValueError('Prepared dataset changed: '+c['id'])
    return report
