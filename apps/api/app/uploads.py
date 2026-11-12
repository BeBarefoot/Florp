"""Bounded source decoding and provenance for the single-page plan contract."""
import hashlib
import io
import warnings

import fitz
from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PIXELS = 45_000_000


def check_size(width, height):
    if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
        raise HTTPException(413, 'Plan exceeds the 45 megapixel decoded limit. Export a smaller image or PDF page.')


def decode(contents, page_index=0):
    if page_index != 0:
        raise HTTPException(422, 'Only the first PDF page is supported. Export the desired page as a separate PDF.')
    manifest = {'schemaVersion': 1, 'sourceSha256': hashlib.sha256(contents).hexdigest(),
                'transforms': []}
    try:
        if contents.startswith(b'%PDF-'):
            with fitz.open(stream=contents, filetype='pdf') as doc:
                if doc.needs_pass or not len(doc):
                    raise HTTPException(422, 'Use an unlocked PDF containing at least one page.')
                page = doc[0]
                # MuPDF raster bounds round outward; check those before allocation.
                rect = (page.rect * fitz.Matrix(2, 2)).irect
                check_size(rect.width, rect.height)
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                manifest.update(sourceFormat='PDF', pageIndex=0, pageCount=len(doc))
                manifest['transforms'].append({'operation': 'pdf-rasterize', 'scale': 2,
                    'pageRotation': page.rotation, 'pageRect': list(page.rect),
                    'cropBox': list(page.cropbox), 'rasterOrigin': [pix.x, pix.y]})
        else:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(contents), formats=['PNG', 'JPEG', 'WEBP']) as source:
                    check_size(*source.size)
                    if getattr(source, 'n_frames', 1) != 1:
                        raise HTTPException(415, 'Animated images are not supported. Export a single PNG or JPEG.')
                    manifest.update(sourceFormat=source.format, sourceSize=list(source.size))
                    orientation = source.getexif().get(274, 1)
                    normalized = ImageOps.exif_transpose(source)
                    manifest['transforms'].append({'operation': 'exif-transpose', 'orientation': orientation})
                    if normalized.mode in ('RGBA', 'LA') or 'transparency' in normalized.info:
                        rgba = normalized.convert('RGBA')
                        image = Image.alpha_composite(Image.new('RGBA', rgba.size, 'white'), rgba).convert('RGB')
                        manifest['transforms'].append({'operation': 'alpha-composite', 'background': [255, 255, 255]})
                    else:
                        image = normalized.convert('RGB')
        check_size(*image.size)
    except HTTPException:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(413, 'Image pixel count too large')
    except (UnidentifiedImageError, OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(415, 'Could not read plan. Use a valid PNG, JPEG, WebP or unlocked PDF.') from exc
    manifest['previewSize'] = list(image.size)
    return image, manifest
