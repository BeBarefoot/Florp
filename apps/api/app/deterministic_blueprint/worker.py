"""Killable one-plan worker. All inputs/outputs are temporary local files."""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import cv2
from .pipeline import BlueprintEngine
from .schema import Options, ExtractionError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--options", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cv2.setNumThreads(8)
    try:
        options = Options.model_validate_json(args.options.read_bytes())
        result = BlueprintEngine(options).process_bytes(args.image.read_bytes())
        args.output.write_bytes(result.archive)
    except ExtractionError as exc:
        print(json.dumps({"code": exc.code, "message": str(exc)}), file=sys.stderr)
        return 2
    except Exception:
        # No tracebacks/host paths in HTTP error bodies. CLI has a stable error.
        print(
            json.dumps(
                {
                    "code": "processing_failed",
                    "message": "Extraction failed; check input and server logs",
                }
            ),
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
