import io
import json

import httpx
import pytest
from PIL import Image

from app import comfy
from app.config import settings
from app.providers import ProviderUnavailable, ProviderOutputError

ASSET = '11111111-1111-4111-8111-111111111111'
JOB = '22222222-2222-4222-8222-222222222222'


@pytest.mark.asyncio
async def test_cloud_depth_submission_polling_and_download(monkeypatch):
    monkeypatch.setattr(settings, 'comfy_api_key', 'test-only')
    calls = []
    png = io.BytesIO()
    Image.new('RGB', (1024, 768), 'brown').save(png, format='PNG')
    async def handle(request):
        calls.append(request)
        if request.url.path == '/api/v2/assets':
            assert b'name="content_type"' in request.content
            assert request.content.index(b'name="file_path"') < request.content.index(b'name="file"')
            return httpx.Response(201, json={'id': ASSET})
        if request.url.path == '/api/v2/jobs':
            assert request.headers['Idempotency-Key'] == JOB
            graph = json.loads(request.content)['workflow']
            assert graph['text']['inputs']['text'] == 'Warm brown bedroom'
            assert graph['depth']['inputs']['image']['info']['id'] == ASSET
            assert graph['condition']['inputs']['pixels'] == ['depth', 0]
            assert not any('Scale' in n['class_type'] or 'Lotus' in n['class_type'] for n in graph.values())
            return httpx.Response(201, json={'id': JOB, 'urls': {'self': f'/api/v2/jobs/{JOB}'}})
        if request.url.path == f'/api/v2/jobs/{JOB}':
            return httpx.Response(200, json={'status': 'succeeded', 'outputs': [
                {'node_id': 'save', 'id': ASSET, 'content_type': 'image/png'}]})
        if request.url.path.endswith('/content'):
            return httpx.Response(302, headers={'Location': 'https://storage.example.test/render.png'})
        assert request.url.host == 'storage.example.test'
        assert 'authorization' not in request.headers
        return httpx.Response(200, content=png.getvalue())
    original = httpx.AsyncClient
    monkeypatch.setattr(comfy.httpx, 'AsyncClient', lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs))
    receipt = await comfy.generate(png.getvalue(), 'Warm brown bedroom', request_key=JOB)
    assert receipt[0] == JOB
    status, image = await comfy.poll(receipt[1])
    assert status == 'complete' and Image.open(io.BytesIO(image)).size == (1024, 768)
    assert len(calls) == 5


@pytest.mark.parametrize('phase', ['queued', 'running', 'failed', 'canceled', 'expired'])
@pytest.mark.asyncio
async def test_cloud_job_states(monkeypatch, phase):
    monkeypatch.setattr(settings, 'comfy_api_key', 'test-only')
    original = httpx.AsyncClient
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={'status': phase}))
    monkeypatch.setattr(comfy.httpx, 'AsyncClient', lambda **kwargs: original(transport=transport, **kwargs))
    if phase in ('queued', 'running'):
        assert await comfy.poll('/api/v2/jobs/' + JOB) == (phase, None)
    else:
        with pytest.raises(ProviderOutputError):
            await comfy.poll('/api/v2/jobs/' + JOB)


def test_provider_selection_and_error_messages_do_not_expose_response(monkeypatch):
    monkeypatch.setattr(settings, 'image_provider', 'auto')
    monkeypatch.setattr(settings, 'comfy_api_key', 'test-only')
    assert comfy.render_config()['provider'] == 'comfy'
    monkeypatch.setattr(settings, 'image_provider', 'fal')
    assert comfy.render_config()['provider'] == 'fal'
    for code in (401, 402, 403, 429):
        with pytest.raises(ProviderUnavailable) as error:
            comfy.checked(httpx.Response(code, text='private upstream response'))
        assert 'private upstream response' not in str(error.value)
    with pytest.raises(ProviderOutputError):
        comfy.cloud_url('https://example.test/api/v2/jobs/abc')
