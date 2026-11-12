"""Comfy Cloud v2: camera-aligned FLUX Depth LoRA workflow, no depth estimator."""
import io
import secrets
from urllib.parse import urljoin, urlsplit
from uuid import UUID

import httpx
from PIL import Image

from .config import settings
from .providers import ProviderConfigurationError, ProviderOutputError, ProviderUnavailable, ProviderRetryableError

BASE = 'https://cloud.comfy.org'
MODEL = 'comfy:flux-depth-lora'


def render_config():
    provider = settings.image_provider
    if provider == 'auto':
        provider = 'comfy' if settings.comfy_api_key else 'fal'
    if provider == 'local-comfy':
        from . import local_comfy
        local_comfy.base_url()
        return dict(provider=provider,configured=True,model=local_comfy.MODEL,checkpoint=settings.local_comfy_checkpoint,controlnet=settings.local_comfy_controlnet)
    if provider not in ('comfy', 'fal'):
        raise ProviderConfigurationError('IMAGE_PROVIDER must be auto, local-comfy, comfy or fal.')
    return dict(provider=provider, configured=bool(settings.comfy_api_key if provider == 'comfy' else settings.image_api_key),
                model=MODEL if provider == 'comfy' else settings.image_model)


def cloud_url(value):
    url = urljoin(BASE, value)
    target = urlsplit(url)
    if target.scheme != 'https' or target.netloc != 'cloud.comfy.org' or not target.path.startswith('/api/v2/'):
        raise ProviderOutputError('Unexpected Comfy Cloud API URL.')
    return url


def headers():
    if not settings.comfy_api_key:
        raise ProviderUnavailable('Set COMFY_API_KEY on the API server to use Comfy Cloud.')
    return {'Authorization': f'Bearer {settings.comfy_api_key}'}


def checked(response):
    # Never echo provider bodies: they may include workflow data or credentials.
    if response.status_code == 401:
        raise ProviderUnavailable('Comfy Cloud authentication failed. Check COMFY_API_KEY on this API server and restart it after changing the key.')
    if response.status_code == 403:
        raise ProviderUnavailable('Comfy Cloud denied account access. Check the API key, account permissions and billing status in your Comfy account.')
    if response.status_code == 402:
        raise ProviderUnavailable('Comfy Cloud is out of credits or requires an active subscription. Add credits to the account associated with COMFY_API_KEY, then explicitly generate a new preview.')
    if response.status_code == 429:
        raise ProviderRetryableError('Comfy Cloud is rate limited or its queue is full. Try later.')
    if response.status_code >= 500:
        raise ProviderRetryableError('Comfy Cloud is temporarily unavailable. Try later.')
    if response.status_code in (400, 422):
        raise ProviderConfigurationError('Comfy Cloud rejected the depth workflow. Check model availability and COMFY_* model settings in the server configuration.')
    response.raise_for_status()
    return response.json()


def workflow(asset_id, prompt, seed):
    def node(kind, **inputs):
        return dict(class_type=kind, inputs=inputs)
    # Based on Comfy-Org/workflow_templates flux_depth_lora_example. Florp
    # already has exact depth, so omit Lotus estimation and all resizing.
    return {
        'depth': node('LoadImage', image={'__type': 'core/ASSET', 'info': {'id': asset_id}}),
        'model': node('UNETLoader', unet_name=settings.comfy_unet, weight_dtype='default'),
        'lora': node('LoraLoaderModelOnly', model=['model', 0], lora_name=settings.comfy_depth_lora, strength_model=1.0),
        'clip': node('DualCLIPLoader', clip_name1=settings.comfy_clip, clip_name2=settings.comfy_t5, type='flux', device='default'),
        'vae': node('VAELoader', vae_name=settings.comfy_vae),
        'text': node('CLIPTextEncode', clip=['clip', 0], text=prompt),
        'guidance': node('FluxGuidance', conditioning=['text', 0], guidance=10.0),
        'negative': node('ConditioningZeroOut', conditioning=['text', 0]),
        'condition': node('InstructPixToPixConditioning', positive=['guidance', 0], negative=['negative', 0],
                          vae=['vae', 0], pixels=['depth', 0]),
        'sample': node('KSampler', model=['lora', 0], positive=['condition', 0], negative=['condition', 1],
                       latent_image=['condition', 2], seed=seed, steps=20, cfg=1.0,
                       sampler_name='euler', scheduler='normal', denoise=1.0),
        'decode': node('VAEDecode', samples=['sample', 0], vae=['vae', 0]),
        'save': node('SaveImage', images=['decode', 0], filename_prefix='Florp'),
    }


async def generate(depth_png, prompt, *, request_key):
    auth = headers()
    async with httpx.AsyncClient(timeout=45) as client:
        asset = checked(await client.post(BASE + '/api/v2/assets', headers=auth,
            data={'content_type': 'image/png', 'file_path': f'florp-{request_key}-depth.png'},
            files={'file': ('depth.png', depth_png, 'image/png')}))
        asset_id = str(UUID(asset['id']))
        graph = workflow(asset_id, prompt, secrets.randbits(48))
        receipt = checked(await client.post(BASE + '/api/v2/jobs',
            headers={**auth, 'Idempotency-Key': request_key}, json={'workflow': graph}))
    job_id = str(UUID(receipt['id']))
    status_url = cloud_url(receipt['urls']['self'])
    return job_id, status_url, status_url


async def poll(status_url):
    auth = headers()
    async with httpx.AsyncClient(timeout=20) as client:
        job = checked(await client.get(cloud_url(status_url), headers=auth))
        phase = job.get('status')
        if phase in ('queued', 'running'):
            return phase, None
        if phase != 'succeeded':
            raise ProviderOutputError('Comfy Cloud did not complete this render. Check the job in your Comfy dashboard before retrying.')
        output = next((o for o in job.get('outputs', []) if o.get('node_id') == 'save'
                       and o.get('content_type') in ('image/png', 'image/jpeg', 'image/webp')), None)
        if not output:
            raise ProviderOutputError('Comfy Cloud returned no image from the render output.')
        # Fetch through the authenticated content endpoint, never an arbitrary
        # workflow-provided URL. The endpoint may redirect to signed storage.
        asset_id = str(UUID(output['id']))
        url = BASE + f'/api/v2/assets/{asset_id}/content'
        # Read the API endpoint with bounded streaming, then follow at most
        # one HTTPS storage redirect, without sending the API key to storage.
        signed_url = None
        async with client.stream('GET', url, headers=auth) as response:
            if response.status_code == 302:
                signed_url = response.headers.get('location', '')
                target = urlsplit(signed_url)
                if target.scheme != 'https' or not target.hostname or target.username or target.password or target.port not in (None, 443):
                    raise ProviderOutputError('Unexpected Comfy image storage URL.')
            else:
                data = await image_bytes(response)
        if signed_url:
            async with client.stream('GET', signed_url) as response:
                data = await image_bytes(response)
    with Image.open(io.BytesIO(data), formats=['PNG', 'JPEG', 'WEBP']) as image:
        if image.size != (1024, 768):
            raise ProviderOutputError('Comfy Cloud returned a different frame size; camera comparison requires 1024 × 768.')
        result = io.BytesIO()
        image.convert('RGB').save(result, format='PNG')
    return 'complete', result.getvalue()


async def image_bytes(response):
    response.raise_for_status()
    data = bytearray()
    async for chunk in response.aiter_bytes():
        if len(data) + len(chunk) > 16 * 1024 * 1024:
            raise ProviderOutputError('Generated image exceeds the download size limit.')
        data.extend(chunk)
    return data
