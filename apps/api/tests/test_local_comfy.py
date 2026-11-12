import io
import json
import httpx
import pytest
from PIL import Image
from app import local_comfy,comfy
from app.config import settings
from app.providers import ProviderConfigurationError

JID='11111111-1111-4111-8111-111111111111'


@pytest.mark.asyncio
async def test_local_submission_and_result_never_use_cloud_credentials(monkeypatch):
    monkeypatch.setattr(settings,'image_provider','local-comfy')
    monkeypatch.setattr(settings,'local_comfy_url','http://127.0.0.1:8188')
    monkeypatch.setattr(settings,'comfy_api_key','must-not-send')
    assert comfy.render_config()['model']==local_comfy.MODEL
    png=io.BytesIO();Image.new('RGB',(1024,768),'white').save(png,format='PNG')
    seen=[]
    def handle(request):
        assert request.url.host=='127.0.0.1'
        assert 'authorization' not in request.headers
        seen.append(request.url.path)
        if request.url.path=='/object_info':
            return httpx.Response(200,json={kind:{'input':{'required':{field:[[name]]}}} for kind,field,name in [
                ('CheckpointLoaderSimple','ckpt_name',settings.local_comfy_checkpoint),('ControlNetLoader','control_net_name',settings.local_comfy_controlnet)]})
        if request.url.path=='/upload/image':return httpx.Response(200,json={'name':'depth.png','subfolder':''})
        if request.url.path=='/prompt':
            graph=json.loads(request.content)['prompt']
            assert graph['latent']['inputs']['width']==1024
            assert graph['condition']['inputs']['image']==['depth',0]
            assert graph['positive']['inputs']['text']=='Warm bedroom'
            assert not any('Preprocessor' in n['class_type'] for n in graph.values())
            return httpx.Response(200,json={'prompt_id':JID})
        if request.url.path.startswith('/history/'):
            return httpx.Response(200,json={JID:{'outputs':{'save':{'images':[{'filename':'image.png','subfolder':'','type':'output'}]}},'status':{'completed':True}}})
        assert request.url.path=='/view'
        return httpx.Response(200,content=png.getvalue())
    original=httpx.AsyncClient
    monkeypatch.setattr(local_comfy.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handle),**kw))
    receipt=await local_comfy.generate(png.getvalue(),'Warm bedroom',request_key=JID)
    status,image=await local_comfy.poll(receipt[1])
    assert status=='complete' and Image.open(io.BytesIO(image)).size==(1024,768)
    assert len(seen)==5


@pytest.mark.parametrize('url',['https://example.com','http://192.168.1.2:8188','http://localhost:8188/path','http://user:pass@localhost:8188'])
def test_local_origin_is_loopback_only(monkeypatch,url):
    monkeypatch.setattr(settings,'local_comfy_url',url)
    with pytest.raises(ProviderConfigurationError):local_comfy.base_url()


@pytest.mark.asyncio
async def test_missing_models_do_not_upload_or_submit(monkeypatch):
    original=httpx.AsyncClient
    def handle(request):
        assert request.url.path=='/object_info'
        return httpx.Response(200,json={})
    monkeypatch.setattr(local_comfy.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handle),**kw))
    with pytest.raises(ProviderConfigurationError,match='missing'):
        await local_comfy.generate(b'depth','style',request_key=JID)


@pytest.mark.asyncio
@pytest.mark.parametrize('job,expected',[({},'queued'),({JID:{'status':{},'outputs':{}}},'running')])
async def test_pending_history(monkeypatch,job,expected):
    original=httpx.AsyncClient
    monkeypatch.setattr(local_comfy.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=job)),**kw))
    assert await local_comfy.poll(local_comfy.base_url()+'/history/'+JID)==(expected,None)
