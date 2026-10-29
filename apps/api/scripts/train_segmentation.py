"""Explicit local segmentation training/evaluation. Never promotes a checkpoint."""
import argparse,json,platform
from pathlib import Path
from app.training_dataset import verify_dataset,digest

def training_options(dataset:Path,model:Path,output:Path,epochs:int,imgsz:int,batch:int,device:str,seed:int)->dict:
    if epochs<1 or imgsz<64 or imgsz%32 or batch<1:raise ValueError('Require epochs/batch >0 and image size a multiple of 32 >=64')
    if not model.is_file():raise ValueError('Provide a trusted local segmentation checkpoint; no implicit download')
    verify_dataset(dataset)
    if output.exists():raise ValueError('Run output already exists')
    return dict(data=str((dataset/'dataset.yaml').resolve()),epochs=epochs,imgsz=imgsz,batch=batch,
                device=device,seed=seed,workers=0,deterministic=True,project=str(output.resolve().parent),
                name=output.name,exist_ok=False,task='segment',mosaic=0.,fliplr=0.,flipud=0.,degrees=0.,
                perspective=0.,hsv_h=0.,hsv_s=0.,hsv_v=.15)

def main():
    p=argparse.ArgumentParser();p.add_argument('--dataset',type=Path,required=True);p.add_argument('--model',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--epochs',type=int,default=100)
    p.add_argument('--imgsz',type=int,default=1024);p.add_argument('--batch',type=int,default=4)
    p.add_argument('--device',default='cpu');p.add_argument('--seed',type=int,default=42)
    p.add_argument('--dry-run',action='store_true');p.add_argument('--test-only',action='store_true')
    a=p.parse_args();options=training_options(a.dataset,a.model,a.output,a.epochs,a.imgsz,a.batch,a.device,a.seed)
    if a.dry_run:print(json.dumps(options,indent=2));return
    import ultralytics
    from ultralytics import YOLO
    model=YOLO(str(a.model))
    if model.task!='segment':raise ValueError('A segmentation checkpoint is required; detection boxes cannot train wall masks')
    provenance={'dataset_provenance_sha256':digest(a.dataset/'provenance.json'),
                'initial_checkpoint_sha256':digest(a.model),'options':options,
                'python':platform.python_version(),'ultralytics':ultralytics.__version__,
                'mode':'held_out_test' if a.test_only else 'train',
                'production_approved':False}
    if a.test_only:
        metrics=model.val(data=options['data'],split='test',imgsz=a.imgsz,batch=a.batch,device=a.device,
                          project=options['project'],name=a.output.name,exist_ok=False)
    else:
        metrics=model.train(**options)
    a.output.mkdir(parents=True,exist_ok=True)
    provenance['metrics']=getattr(metrics,'results_dict',{})
    (a.output/'florp-run.json').write_text(json.dumps(provenance,indent=2,default=str))
    print('Completed. Model metrics do not establish graph accuracy. Run held-out end-to-end evaluation before promotion.')
if __name__=='__main__':main()
