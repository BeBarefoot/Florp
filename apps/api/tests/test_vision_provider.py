from unittest.mock import AsyncMock, patch
import json
import httpx
import pytest
from app.geometry import fallback_geometry
from app.providers import extract_geometry, ProviderOutputError

class MockClient:
    calls=[]
    async def __aenter__(self):return self
    async def __aexit__(self,*args):return None
    async def post(self,url,headers,json):
        self.calls.append(json)
        if len(self.calls)==1:
            data={'choices':[{'finish_reason':'length','message':{'content':'{"width_px":800'}}]}
        else:
            obj=fallback_geometry(800,600).model_dump()
            data={'choices':[{'finish_reason':'stop','message':{'content':__import__('json').dumps(obj)}}]}
        return httpx.Response(200,json=data,request=httpx.Request('POST',url))

@pytest.mark.asyncio
async def test_truncated_json_is_retried(monkeypatch):
    from app import providers
    fake=MockClient()
    fake.calls=[]
    monkeypatch.setattr(providers.httpx,'AsyncClient',lambda **_:fake)
    monkeypatch.setattr(providers.settings,'llm_api_key','test-key')
    result=await extract_geometry(b'raw','image/png',800,600)
    assert result.width_px==800
    assert len(fake.calls)==2

def test_malformed_json_gets_actionable_error():
    from app.providers import _parse_geometry_content
    with pytest.raises(ProviderOutputError,match='incomplete or invalid'):
        _parse_geometry_content('{"width_px":')
