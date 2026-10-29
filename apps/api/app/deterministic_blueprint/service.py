"""uvicorn app.deterministic_blueprint.service:app --host 127.0.0.1 --port 8010

This is opt-in and deliberately does not modify the existing Florp editor.
"""

from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError
from .schema import Options
from .preprocess import MAX_UPLOAD_BYTES

TIMEOUT = min(20.0, max(0.1, float(os.environ.get("BLUEPRINT_TIMEOUT_SECONDS", "4.8"))))
slots = asyncio.Semaphore(1)


@asynccontextmanager
async def lifespan(app):
    yield


app = FastAPI(
    title="Florp Deterministic Blueprint Engine", version="1.0.0", lifespan=lifespan
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "runtime": "local_cpu_only",
        "deadline_seconds": TIMEOUT,
        "concurrent_plans_per_worker": 1,
        "downloads": False,
    }


async def stop_process(process):
    try:
        # OCR may still hold the stderr pipe after its parent worker exits.
        # Kill the process group even when the worker already has a return code.
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        elif process.returncode is None:
            process.kill()
    except ProcessLookupError:
        pass
    await process.communicate()


async def extract_with_deadline(data: bytes, options: Options, timeout: float):
    with tempfile.TemporaryDirectory(prefix="florp-cv-") as folder:
        root = Path(folder)
        image, settings, output = (
            root / "input",
            root / "options.json",
            root / "result.zip",
        )
        image.write_bytes(data)
        settings.write_text(options.model_dump_json())
        environment = {
            **os.environ,
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
        }
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.deterministic_blueprint.worker",
            "--image",
            str(image),
            "--options",
            str(settings),
            "--output",
            str(output),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            env=environment,
            start_new_session=(os.name == "posix"),
        )
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            await stop_process(process)
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise HTTPException(
                504,
                detail={
                    "code": "deadline_exceeded",
                    "message": "Processing budget exceeded; no partial geometry returned. Crop/downsample, or set ocr=false with an explicit reference/default scale.",
                },
            )
        if process.returncode:
            try:
                error = json.loads(stderr.decode().splitlines()[-1])
            except (ValueError, IndexError):
                error = {
                    "code": "worker_failed",
                    "message": "Worker failed without an extraction result",
                }
            raise HTTPException(422 if process.returncode == 2 else 500, detail=error)
        if not output.exists():
            raise HTTPException(
                500,
                detail={
                    "code": "missing_result",
                    "message": "Worker returned no archive",
                },
            )
        return output.read_bytes()


@app.post(
    "/extract",
    responses={
        200: {"content": {"application/zip": {}}},
        422: {"description": "Calibration/geometry cannot be inferred safely"},
        429: {"description": "CPU worker occupied"},
        504: {"description": "Processing deadline exceeded"},
    },
)
async def extract(file: UploadFile = File(...), options: str = Form("{}")):
    started = time.perf_counter()
    if len(options) > 16384:
        raise HTTPException(
            422,
            detail={
                "code": "invalid_options",
                "message": "Options JSON exceeds 16 KiB",
            },
        )
    try:
        settings = Options.model_validate_json(options)
    except ValidationError as exc:
        raise HTTPException(
            422, detail={"code": "invalid_options", "message": str(exc)}
        )
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413,
            detail={
                "code": "input_too_large",
                "message": "PNG/JPEG required, maximum 24 MiB",
            },
        )
    try:
        await asyncio.wait_for(slots.acquire(), timeout=0.01)
    except asyncio.TimeoutError:
        raise HTTPException(
            429,
            detail={
                "code": "worker_busy",
                "message": "One plan is already processing; retry after it completes",
            },
            headers={"Retry-After": "1"},
        )
    try:
        remaining = TIMEOUT - (time.perf_counter() - started)
        if remaining <= 0:
            raise HTTPException(
                504,
                detail={
                    "code": "deadline_exceeded",
                    "message": "Request input exhausted processing budget",
                },
            )
        archive = await extract_with_deadline(data, settings, remaining)
    finally:
        slots.release()
    elapsed = time.perf_counter() - started
    if elapsed >= TIMEOUT:
        raise HTTPException(
            504,
            detail={
                "code": "deadline_exceeded",
                "message": "Output exceeded processing budget; no partial output returned",
            },
        )
    return Response(
        archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="florp-walls.zip"',
            "X-Processing-Seconds": f"{elapsed:.6f}",
            "X-Accuracy-Status": "requires-review",
        },
    )
