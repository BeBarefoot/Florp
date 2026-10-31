"""Snapshot a user-corrected plan as a gold fixture.

Example (from apps/api):
  uv run python scripts/snapshot_gold.py --blueprint <id> --name case1

Copies the blueprint's preview.png and its latest PlanRevision model into
data/gold/<name>/ (gitignored: these are real client drawings).
"""

from __future__ import annotations
import argparse, json, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlmodel import Session, create_engine, select
from app.config import settings
from app.models import Blueprint, PlanRevision

GOLD = Path(__file__).resolve().parents[1] / "data" / "gold"


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--blueprint", required=True)
    parser.add_argument("--name", required=True)
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
        out = GOLD / args.name
        out.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(bp.preview_path, out / "preview.png")
        (out / "gold.json").write_text(json.dumps(row.model, indent=2))
        thresholds = out / "thresholds.json"
        if not thresholds.exists():
            thresholds.write_text("{}")
        print(f"Saved {out} (revision {row.revision})")


if __name__ == "__main__":
    main()
