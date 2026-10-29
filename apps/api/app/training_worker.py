"""Serialized local training with durable status, cooperative cancellation and resume."""
import json, os, sys, time, fcntl
from pathlib import Path
from datetime import datetime, timezone

def atomic_json(path, value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2,default=str))
    with temp.open('rb') as f:os.fsync(f.fileno())
    os.replace(temp,path)

def execute(folder:Path):
    path=folder/'job.json';job=json.loads(path.read_text())
    process_lock=(folder/'process.lock').open('a')
    try:fcntl.flock(process_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:return
    def update(**kw):
        job.update(kw);atomic_json(path,job)
    def cancelled():return (folder/'cancel').exists()
    update(status='queued',pid=os.getpid(),started_at=datetime.now(timezone.utc).isoformat())
    try:
        lock=(folder.parent/'training.lock').open('a')
        while True:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:
                if cancelled():update(status='cancelled');return
                time.sleep(1)
        if cancelled():update(status='cancelled');return
        from .training_dataset import digest,verify_dataset
        if digest(Path(job['checkpoint']))!=job['checkpoint_sha256']:raise ValueError('Checkpoint changed after submission')
        verify_dataset(Path(job['dataset']))
        from ultralytics import YOLO
        import ultralytics,torch,platform
        if job['device']=='mps' and not torch.backends.mps.is_available():raise ValueError('MPS unavailable; submit a CPU run')
        from scripts.train_segmentation import training_options
        resume=job.get('resume',False)
        model=YOLO(str(folder/'output'/'weights'/'last.pt') if resume else job['checkpoint'])
        if model.task!='segment':raise ValueError('Segmentation checkpoint required')
        update(status='running',environment={'python':platform.python_version(),'torch':torch.__version__,'ultralytics':ultralytics.__version__})
        def progress(trainer):
            update(epoch=int(trainer.epoch)+1,metrics=getattr(trainer,'metrics',{}))
            if cancelled():trainer.stop=True
        model.add_callback('on_train_epoch_end',progress)
        options=({'resume':True,'device':job['device'],'data':str(Path(job['dataset'])/'dataset.yaml')} if resume else training_options(Path(job['dataset']),Path(job['checkpoint']),folder/'output',job['epochs'],1024,job['batch'],job['device'],job['seed']))
        metrics=model.train(**options)
        if not cancelled():
            from .dataset_evaluation import compare_checkpoints
            evaluation=folder/('validation-'+str(time.time_ns()))
            compare_checkpoints(Path(job['dataset']),Path(job['checkpoint']),folder/'output'/'weights'/'best.pt',evaluation,job['device'])
            update(validation_report=str(evaluation.name+'/report.json'))
        update(status='cancelled' if cancelled() else 'completed',completed_at=datetime.now(timezone.utc).isoformat(),metrics=getattr(metrics,'results_dict',{}),production_approved=False)
    except BaseException as e:
        update(status='failed',error=str(e),completed_at=datetime.now(timezone.utc).isoformat());raise
    finally:
        process_lock.close()
if __name__=='__main__':execute(Path(sys.argv[1]))
