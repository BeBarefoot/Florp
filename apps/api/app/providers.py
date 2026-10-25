import json
import httpx
from .config import settings
from .geometry import Geometry
class ProviderUnavailable(RuntimeError): pass
class ProviderAuthenticationError(ProviderUnavailable): pass
class ProviderConfigurationError(ProviderUnavailable): pass
class ProviderOutputError(ProviderUnavailable): pass

def _parse_geometry_content(content: str) -> Geometry:
    from pydantic import ValidationError
    cleaned=content.strip()
    if cleaned.startswith('```'):
        cleaned=cleaned.split('\n',1)[-1].rsplit('```',1)[0].strip()
    try:
        return Geometry.model_validate_json(cleaned)
    except ValidationError as exc:
        raise ProviderOutputError('Vision model produced incomplete or invalid geometry JSON. Retry extraction or choose a model with reliable structured JSON support. No draft was overwritten.') from exc

async def extract_geometry(image_bytes:bytes,mime:str,width:int,height:int)->Geometry:
    import base64
    if not settings.llm_api_key:
        raise ProviderUnavailable('LLM_API_KEY is missing in apps/api/.env')
    # Keep instructions short to reduce the chance of model output truncation.
    prompt=(
       'Read this architectural floor plan. Return ONLY one compact JSON object (no markdown). '
       'Keys: width_px, height_px, px_per_meter (number or null), rooms, walls, openings, warnings. '
       'Room: id,label,points:[{x,y}],confidence. '
       'Wall: id,start:{x,y},end:{x,y},thickness_m,height_m,inferred. '
       'Opening: id,kind (door/window),wall_id,offset_m,width_m,height_m,sill_m,inferred. '
       'Use pixel coordinates from the image, origin upper left. Use actual image dimensions '
       +str(width)+'x'+str(height)+'. Unknown information must be omitted from arrays; '
       'do not invent dimensions, doors, windows or room geometry. '
       'If an opening is uncertain, leave it out. Do not include pixel-to-meter scale unless supported.'
    )
    b64=base64.b64encode(image_bytes).decode()
    headers={'Authorization':f'Bearer {settings.llm_api_key}'}
    url=settings.llm_base_url.rstrip('/')+'/chat/completions'
    body={'model':settings.llm_model,
          'messages':[{'role':'user','content':[{'type':'text','text':prompt},
                {'type':'image_url','image_url':{'url':f'data:{mime};base64,{b64}'}}]}],
          'max_completion_tokens':settings.llm_max_completion_tokens}
    # A truncated response can be retried once with a tighter response instruction.
    for attempt in range(2):
        request=dict(body)
        if attempt:
            request['messages']=[dict(body['messages'][0])]
            request['messages'][0]['content']=[
                {'type':'text','text':prompt+' Very short JSON. Limit to 20 most important walls and 8 rooms; prioritize completeness and valid JSON.'},
                body['messages'][0]['content'][1]]
        async with httpx.AsyncClient(timeout=180) as client:
            response=await client.post(url,headers=headers,json=request)
        if response.status_code in (401,403):
            raise ProviderAuthenticationError('Vision API authentication failed (HTTP '+str(response.status_code)+'). Confirm LLM_API_KEY and LLM_BASE_URL; ChatGPT Plus is not an API key.')
        if response.status_code==404:
            raise ProviderConfigurationError('Vision endpoint or model returned HTTP 404. Check the provider base URL and that LLM_MODEL is supported by that provider.')
        if response.status_code in (400,413,422):
            raise ProviderConfigurationError('Vision provider rejected the request (HTTP '+str(response.status_code)+'). Confirm image support and max_completion_tokens for this model. '+response.text[:220])
        if response.status_code==429:
            raise ProviderUnavailable('Vision provider rate or quota limit reached (HTTP 429). Try later or use local pretrained extraction.')
        response.raise_for_status()
        try:
            choice=response.json()['choices'][0]
            content=choice['message'].get('content') or ''
            finish=choice.get('finish_reason')
        except (KeyError,IndexError,TypeError,ValueError) as exc:
            raise ProviderOutputError('Vision provider returned an unexpected response format.') from exc
        if finish in ('length','max_tokens') or not isinstance(content,str) or not content.strip():
            if attempt==0:continue
            raise ProviderOutputError('Vision output was truncated by model completion limit. Increase LLM_MAX_COMPLETION_TOKENS or choose a model with higher output capacity.')
        try:
            parsed=_parse_geometry_content(content)
            if (parsed.width_px,parsed.height_px)!=(width,height):
                raise ProviderOutputError('Model returned coordinates for the wrong image dimensions.')
            return parsed
        except ProviderOutputError:
            if attempt==0:continue
            raise
    raise ProviderOutputError('Model could not produce a complete valid geometry object after two attempts.')

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
