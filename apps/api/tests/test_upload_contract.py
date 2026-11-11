import hashlib
import io
import json
from pathlib import Path
import fitz
import pytest
from fastapi import HTTPException
from PIL import Image
from app import uploads
from app.config import settings
from test_plan_api import client


def encoded(fmt='PNG', exif=None):
    out = io.BytesIO()
    Image.new('RGB', (80, 40), 'white').save(out, format=fmt, **({'exif': exif} if exif else {}))
    return out.getvalue()


@pytest.mark.parametrize('fmt', ['PNG', 'JPEG', 'WEBP'])
def test_supported_images(fmt):
    raw = encoded(fmt)
    image, meta = uploads.decode(raw)
    assert image.size == (80, 40)
    assert meta['sourceFormat'] == fmt
    assert meta['sourceSha256'] == hashlib.sha256(raw).hexdigest()


def test_exif_orientation():
    exif = Image.Exif()
    exif[274] = 6
    image, meta = uploads.decode(encoded('JPEG', exif))
    assert image.size == (40, 80)
    assert meta['sourceSize'] == [80, 40]
    assert meta['transforms'] == [{'operation': 'exif-transpose', 'orientation': 6}]


def test_limit_checked_before_decode(monkeypatch):
    monkeypatch.setattr(uploads, 'MAX_PIXELS', 100)
    monkeypatch.setattr(uploads.ImageOps, 'exif_transpose', lambda _: pytest.fail('decoded oversized source'))
    with pytest.raises(HTTPException) as error:
        uploads.decode(encoded())
    assert error.value.status_code == 413


def test_pdf_contract(monkeypatch):
    with fitz.open() as doc:
        doc.new_page(width=100, height=70)
        doc.new_page(width=200, height=150)
        raw = doc.tobytes()
    image, meta = uploads.decode(raw)
    assert image.size == (200, 140)
    assert meta['pageIndex'] == 0 and meta['pageCount'] == 2
    with pytest.raises(HTTPException) as error:
        uploads.decode(raw, 1)
    assert error.value.status_code == 422
    monkeypatch.setattr(uploads, 'MAX_PIXELS', 100)
    monkeypatch.setattr(fitz.Page, 'get_pixmap', lambda *a, **kw: pytest.fail('rasterized oversized PDF'))
    with pytest.raises(HTTPException) as error:
        uploads.decode(raw)
    assert error.value.status_code == 413


def test_rejected_upload_preserves_project_and_valid_upload_records_hashes(client, tmp_path, monkeypatch):
    c, _ = client
    monkeypatch.setattr(settings, 'storage_path', str(tmp_path / 'uploads'))
    pid = c.get('/projects').json()[0]['id']
    before = c.get(f'/projects/{pid}/blueprints').json()
    for raw in (b'not an image', b'%PDF-broken', encoded('GIF')):
        response = c.post(f'/projects/{pid}/blueprints', files={'file': ('bad.png', raw)})
        assert response.status_code == 415
        assert c.get(f'/projects/{pid}/blueprints').json() == before
    raw = encoded()
    response = c.post(f'/projects/{pid}/blueprints', files={'file': ('plan.png', raw)})
    assert response.status_code == 200, response.text
    folder = Path(settings.storage_path) / response.json()['id']
    meta = json.loads((folder / 'source-manifest.json').read_text())
    assert meta['sourceSha256'] == hashlib.sha256(raw).hexdigest()
    assert meta['previewSha256'] == hashlib.sha256((folder / 'preview.png').read_bytes()).hexdigest()
    assert (folder / 'original.bin').read_bytes() == raw
