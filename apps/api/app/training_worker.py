"""Local worker preserves run logs and failure metadata across API restarts."""
import json,os,sys,subprocess
from pathlib import Path
from datetime import datetime,timezone

def execute(folder:Path):
    path=folder/'job.json';job=json.loads(path.read_text())
    def update(**kw):
        job.update(kw);temp=path.with_suffix('.tmp');temp.write_text(json.dumps(job,indent=2));os.replace(temp,path)
    update(status='running',pid=os.getpid(),started_at=datetime.now(timezone.utc).isoformat())
    try:
        import fcntl
        lock=(folder.parent/'training.lock').open('a')
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Another training run is active; retry after it completes')
        from .training_dataset import digest,verify_dataset
        if digest(Path(job['checkpoint']))!=job['checkpoint_sha256']:raise ValueError('Checkpoint changed after submission')
        verify_dataset(Path(job['dataset']))
        from ultralytics import YOLO
        import torch
        if job['device']=='mps' and not torch.backends.mps.is_available():raise ValueError('MPS unavailable; submit a CPU run')
        if YOLO(job['checkpoint']).task!='segment':raise ValueError('Segmentation checkpoint required')
        args=[sys.executable,'-m','scripts.train_segmentation','--dataset',job['dataset'],'--model',job['checkpoint'],'--output',str(folder/'output'),'--device',job['device'],'--epochs',str(job['epochs']),'--batch',str(job['batch']),'--seed',str(job['seed'])]
        result=subprocess.run(args,check=False)
        if result.returncode:raise RuntimeError('Trainer exited '+str(result.returncode)+'; inspect worker log')
        update(status='completed',completed_at=datetime.now(timezone.utc).isoformat(),production_approved=False)
    except BaseException as e:
        update(status='failed',error=str(e),completed_at=datetime.now(timezone.utc).isoformat());raise
if __name__=='__main__':execute(Path(sys.argv[1]))
