"""Create a synthetic, calibrated demo through the running local API; no paid calls."""
import argparse
import io
import json
from urllib.parse import urlsplit

import httpx
from PIL import Image, ImageDraw


def fixtures():
    image = Image.new('RGB', (800, 600), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 100, 700, 500), outline=(190, 70, 70), width=14)
    draw.line((400, 100, 400, 500), fill=(190, 70, 70), width=14)
    draw.line((100, 550, 700, 550), fill='black', width=1)
    draw.text((330, 560), 'Synthetic reference: 6 metres', fill='black')
    for extension, kind, mime in [('png','PNG','image/png'), ('jpg','JPEG','image/jpeg'), ('pdf','PDF','application/pdf')]:
        buf = io.BytesIO()
        image.save(buf, format=kind, **({'resolution':144} if kind=='PDF' else {}))
        yield f'synthetic-plan.{extension}', mime, buf.getvalue()


def create_demo(api='http://127.0.0.1:8000'):
    parsed = urlsplit(api)
    if parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('Demo creation is restricted to your local Florp API')
    with httpx.Client(base_url=api.rstrip('/'), timeout=40) as client:
        def checked(response):
            response.raise_for_status()
            return response.json()
        project = checked(client.post('/projects', json={'title':'Synthetic demo — not a real property'}))
        results=[]
        for name,mime,raw in fixtures():
            bp=checked(client.post(f"/projects/{project['id']}/blueprints",files={'file':(name,raw,mime)}))
            url=f"/blueprints/{bp['id']}/plan"
            extracted=checked(client.post(url+'/extract?expected_revision=0'))
            model=extracted['model']
            if not model['walls'] or not model['rooms']:
                raise RuntimeError(f'Synthetic extraction produced no usable rooms for {name}; inspect the demo project.')
            # This is generated ground truth, not inferred scale on a user's scan.
            model['scale']={'reference':{'p1':{'x':100,'y':550},'p2':{'x':700,'y':550},'lengthMeters':6}}
            saved=checked(client.put(url,json={'expectedRevision':extracted['revision'],'model':model}))
            results.append({'id':bp['id'],'filename':name,'revision':saved['revision'],
                            'walls':len(saved['model']['walls']),'rooms':len(saved['model']['rooms'])})
        return {'projectId':project['id'],'projectUrl':f"http://localhost:3000/project/{project['id']}",
                'blueprints':results,'note':'Review is intentionally left draft. No external model or image provider was called.'}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api',default='http://127.0.0.1:8000')
    args=parser.parse_args()
    try:
        print(json.dumps(create_demo(args.api),indent=2))
    except (ValueError,RuntimeError,httpx.HTTPError) as exc:
        parser.exit(1,f'Demo could not complete: {exc}\nStart the local API and inspect any partial Synthetic demo project.\n')
