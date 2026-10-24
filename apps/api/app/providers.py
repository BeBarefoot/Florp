import json
import httpx
from .config import settings
from .geometry import Geometry
class ProviderUnavailable(RuntimeError): pass
async def extract_geometry(image_bytes:bytes,mime:str,width:int,height:int)->Geometry:
    if not settings.llm_api_key: raise ProviderUnavailable('LLM_API_KEY is missing. Add it to apps/api/.env')
    schema=Geometry.model_json_schema()
    prompt=("Analyze this architectural floor plan. Return geometrical evidence only. "
            "All coordinates are in original image pixels, origin at top left. "
            "Do not invent exact measurements; use null scale if uncertain. "
            "Wall segments must be shared between rooms. Openings must refer to wall IDs. "
            f"Image width {width}px, height {height}px. Respond ONLY with JSON matching: {json.dumps(schema)}")
    import base64
    b64=base64.b64encode(image_bytes).decode()
    body={'model':settings.llm_model,'temperature':0,'messages':[{'role':'user','content':[{'type':'text','text':prompt},{'type':'image_url','image_url':{'url':f'data:{mime};base64,{b64}'}}]}]}
    async with httpx.AsyncClient(timeout=150) as c:
        r=await c.post(settings.llm_base_url.rstrip('/')+'/chat/completions',headers={'Authorization':f'Bearer {settings.llm_api_key}'},json=body)
        r.raise_for_status()
        content=r.json()['choices'][0]['message']['content']
    if content.strip().startswith('```'):
        content=content.split('\n',1)[1].rsplit('```',1)[0]
    return Geometry.model_validate_json(content)
async def generate_image(depth_png:bytes,prompt:str)->tuple[str,str]:
    # Real queue API adapter. The initial implementation submits and returns provider URLs,
    # and the caller must explicitly poll for completion.
    if not settings.image_api_key: raise ProviderUnavailable('IMAGE_API_KEY is missing. Add it to apps/api/.env')
    import base64
    data_url='data:image/png;base64,'+base64.b64encode(depth_png).decode()
    endpoint=f"{settings.fal_api_base.rstrip('/')}/{settings.image_model}"
    async with httpx.AsyncClient(timeout=60) as c:
        r=await c.post(endpoint,headers={'Authorization':f'Key {settings.image_api_key}','Content-Type':'application/json'},json={'prompt':prompt,'control_image_url':data_url,'image_size':'landscape_4_3'})
        r.raise_for_status()
        obj=r.json()
    return obj.get('request_id',''),obj.get('status_url','')
