"""Local ComfyUI core SDXL + depth ControlNet; no cloud calls or credentials."""
import hashlib
import io
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from PIL import Image
from .config import settings
from .providers import ProviderConfigurationError, ProviderOutputError, ProviderRetryableError

MODEL = 'local-comfy:sdxl-depth'


def base_url():
    value = settings.local_comfy_url.rstrip('/')
    u = urlsplit(value)
    if u.scheme != 'http' or u.hostname not in ('127.0.0.1', 'localhost', '::1') or u.username or u.password or u.path or u.query or u.fragment:
        raise ProviderConfigurationError('LOCAL_COMFY_URL must be a loopback HTTP origin, e.g. http://127.0.0.1:8188.')
    return value


def checked(response):
    if response.status_code == 429 or response.status_code >= 500:
        raise ProviderRetryableError('Local ComfyUI is temporarily unavailable. Keep it running; Florp will check saved jobs again.')
    if response.status_code >= 400:
        raise ProviderConfigurationError('Local ComfyUI rejected the request. Check its terminal, checkpoint and depth ControlNet settings.')
    return response.json()


def workflow(image, prompt, seed):
    def node(kind, **inputs):
        return dict(class_type=kind, inputs=inputs)
    return {
        'model':node('CheckpointLoaderSimple', ckpt_name=settings.local_comfy_checkpoint),
        'depth':node('LoadImage', image=image),
        'control':node('ControlNetLoader', control_net_name=settings.local_comfy_controlnet),
        'positive':node('CLIPTextEncode', text=prompt, clip=['model',1]),
        'negative':node('CLIPTextEncode', text='distorted walls, extra doors, missing windows, warped perspective', clip=['model',1]),
        'condition':node('ControlNetApplyAdvanced',positive=['positive',0],negative=['negative',0],control_net=['control',0],image=['depth',0],strength=0.85,start_percent=0.0,end_percent=1.0),
        'latent':node('EmptyLatentImage',width=1024,height=768,batch_size=1),
        'sample':node('KSampler',model=['model',0],positive=['condition',0],negative=['condition',1],latent_image=['latent',0],seed=seed,steps=20,cfg=7.0,sampler_name='euler',scheduler='normal',denoise=1.0),
        'decode':node('VAEDecode',samples=['sample',0],vae=['model',2]),
        'save':node('SaveImage',images=['decode',0],filename_prefix='Florp'),
    }


async def generate(depth_png, prompt, *, request_key):
    base = base_url()
    async with httpx.AsyncClient(timeout=45, follow_redirects=False) as client:
        info = checked(await client.get(base+'/object_info'))
        for kind, field, value in [('CheckpointLoaderSimple','ckpt_name',settings.local_comfy_checkpoint),('ControlNetLoader','control_net_name',settings.local_comfy_controlnet)]:
            choices = info.get(kind,{}).get('input',{}).get('required',{}).get(field,[[]])[0]
            if value not in choices:
                raise ProviderConfigurationError('Local ComfyUI is missing the configured SDXL checkpoint or compatible SDXL depth ControlNet. Check LOCAL_COMFY_CHECKPOINT and LOCAL_COMFY_CONTROLNET.')
        uploaded = checked(await client.post(base+'/upload/image', data={'type':'input','overwrite':'false'},
                        files={'image':(f'florp-{request_key}.png',depth_png,'image/png')}))
        name, folder = uploaded['name'], uploaded.get('subfolder','')
        path = PurePosixPath(folder)/name
        if path.is_absolute() or '..' in path.parts or '\\' in str(path):
            raise ProviderOutputError('Invalid local ComfyUI upload path.')
        seed = int(hashlib.sha256(request_key.encode()).hexdigest()[:12],16)
        receipt = checked(await client.post(base+'/prompt',json={'prompt':workflow(str(path),prompt,seed),'client_id':request_key}))
        job_id = str(UUID(receipt['prompt_id']))
    url = base+'/history/'+job_id
    return job_id,url,url


async def poll(status_url):
    base = base_url()
    prefix = base+'/history/'
    if not status_url.startswith(prefix):
        raise ProviderConfigurationError('Local ComfyUI address changed. Restore LOCAL_COMFY_URL to recover this job.')
    jid = str(UUID(status_url[len(prefix):]))
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        history = checked(await client.get(prefix+jid))
        job = history.get(jid)
        if not job:
            return 'queued',None
        if job.get('status',{}).get('status_str') == 'error':
            raise ProviderOutputError('Local ComfyUI could not run the workflow. Check its terminal for model or memory errors; then explicitly generate a new preview.')
        images = job.get('outputs',{}).get('save',{}).get('images',[])
        if not images:
            if job.get('status',{}).get('completed'):
                raise ProviderOutputError('Local ComfyUI completed without the expected image output.')
            return 'running',None
        output = images[0]
        name, folder = output['filename'], output.get('subfolder','')
        path = PurePosixPath(folder)/name
        if path.is_absolute() or '..' in path.parts or '\\' in str(path) or output.get('type') != 'output':
            raise ProviderOutputError('Unexpected local ComfyUI output path.')
        from .comfy import image_bytes
        async with client.stream('GET',base+'/view',params={'filename':name,'subfolder':folder,'type':'output'}) as response:
            data = await image_bytes(response)
    with Image.open(io.BytesIO(data),formats=['PNG','JPEG','WEBP']) as image:
        if image.size != (1024,768):
            raise ProviderOutputError('Local ComfyUI returned a different frame size; expected 1024 × 768.')
        out = io.BytesIO()
        image.convert('RGB').save(out,format='PNG')
    return 'complete',out.getvalue()
