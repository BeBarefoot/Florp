"""Snapshot a user-corrected plan as a gold fixture.

Example (from apps/api):
  uv run python scripts/snapshot_gold.py --blueprint <id> --name case1

Copies the blueprint's preview.png and its latest PlanRevision model into
data/gold/<name>/ (gitignored: these are real client drawings).
"""

from __future__ import annotations
import argparse, hashlib, json, shutil, sys, re, tempfile, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlmodel import Session, create_engine, select
from app.config import settings
from app.models import Blueprint, PlanRevision

GOLD = Path(__file__).resolve().parents[1] / "data" / "gold"


def write_snapshot(source, model, root, name, replace=False):
    from app.plan_model import PlanModel
    from app.plan_score import READINESS_MINIMUMS

    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
        raise ValueError(
            "Use a simple case name with letters, numbers, dashes or underscores"
        )
    model = PlanModel.model_validate(model)
    if not model.walls or any(o.status == "proposed" for o in model.openings):
        raise ValueError(
            "Finish reviewing openings and save the reference geometry first"
        )
    source = Path(source)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    out = root / name
    if out.exists() and not replace:
        raise ValueError(
            "Snapshot exists; use --replace to archive it and write a new revision"
        )
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        stage = Path(tmp) / "case"
        stage.mkdir()
        shutil.copyfile(source, stage / "preview.png")
        (stage / "gold.json").write_text(model.model_dump_json(indent=2))
        (stage / "thresholds.json").write_text(json.dumps(READINESS_MINIMUMS, indent=2))
        (stage / "metadata.json").write_text(
            json.dumps(
                {
                    "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "revision": model.revision,
                    "annotation_origin": "saved-editor-revision",
                },
                indent=2,
            )
        )
        backup = None
        if out.exists():
            archive = root / ".history"
            archive.mkdir(exist_ok=True)
            backup = archive / (name + "-" + uuid.uuid4().hex)
            out.rename(backup)
        try:
            stage.rename(out)
        except OSError:
            if backup:
                backup.rename(out)
            raise
    return out


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--blueprint", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="archive an existing snapshot before replacing it",
    )
    args = parser.parse_args()
    engine = create_engine(settings.database_url)
    with Session(engine) as s:
        bp = s.get(Blueprint, args.blueprint)
        if not bp:
            parser.error("unknown blueprint")
        row = s.exec(
            select(PlanRevision)
            .where(PlanRevision.blueprint_id == args.blueprint)
            .order_by(PlanRevision.revision.desc())
        ).first()
        if not row:
            parser.error("blueprint has no saved plan revision")
        try:
            out = write_snapshot(
                bp.preview_path, row.model, GOLD, args.name, args.replace
            )
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        print(f"Saved {out} (revision {row.revision})")


if __name__ == "__main__":
    main()
