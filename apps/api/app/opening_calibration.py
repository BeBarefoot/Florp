"""Explicit local threshold calibration from reviewed reference predictions.

Scores are heuristic evidence, not probabilities. Writing a profile does not
activate it; an administrator must configure OPENING_CONFIDENCE_PROFILE.
"""

from __future__ import annotations
from pathlib import Path
from typing import Literal
import hashlib, json, math
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .plan_model import PlanModel


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    version: Literal[1] = 1
    thresholds: dict[str, float]
    source_hashes: list[str] = Field(min_length=3)
    minimum_examples: int = Field(default=10, ge=1)
    minimum_precision: float = Field(default=0.95, ge=0.5, le=1)
    empirical_precision: dict[str, float | None]
    sample_counts: dict[str, int]

    @model_validator(mode="after")
    def valid(self):
        kinds = {"door", "window"}
        if (
            set(self.thresholds) != kinds
            or set(self.empirical_precision) != kinds
            or set(self.sample_counts) != kinds
        ):
            raise ValueError(
                "Profile must cover doors and windows only; garages always require approval"
            )
        if any(
            not math.isfinite(t) or not 0.7 <= t <= 1.01
            for t in self.thresholds.values()
        ):
            raise ValueError(
                "Thresholds must be in [0.7,1.01]; 1.01 disables automatic approval"
            )
        if len(set(self.source_hashes)) != len(self.source_hashes) or any(
            len(h) != 64 or any(c not in "0123456789abcdef" for c in h)
            for h in self.source_hashes
        ):
            raise ValueError("Profile needs unique SHA-256 source identities")
        if any(n < 0 for n in self.sample_counts.values()) or any(
            p is not None and (not math.isfinite(p) or not 0 <= p <= 1)
            for p in self.empirical_precision.values()
        ):
            raise ValueError("Invalid calibration statistics")
        for kind in kinds:
            if self.thresholds[kind] <= 1 and (
                self.sample_counts[kind] < self.minimum_examples
                or self.empirical_precision[kind] is None
                or self.empirical_precision[kind] < self.minimum_precision
            ):
                raise ValueError(
                    "Automatic approval threshold lacks supporting reference samples"
                )
        return self


def tune(observations, source_hashes, min_precision=0.95, min_examples=10):
    if not 0.5 <= min_precision <= 1 or min_examples < 1:
        raise ValueError("Invalid calibration precision/sample requirement")
    thresholds = {}
    precision = {}
    counts = {}
    for kind in ("door", "window"):
        samples = observations.get(kind, [])
        if any(not math.isfinite(c) or not 0 <= c <= 1 for c, _ in samples):
            raise ValueError("Invalid evidence score")
        thresholds[kind] = 1.01
        precision[kind] = None
        counts[kind] = 0
        for threshold in sorted({max(0.7, c) for c, _ in samples}):
            selected = [correct for c, correct in samples if c >= threshold]
            if (
                len(selected) >= min_examples
                and sum(selected) / len(selected) >= min_precision
            ):
                thresholds[kind] = threshold
                precision[kind] = sum(selected) / len(selected)
                counts[kind] = len(selected)
                break
    return Profile(
        thresholds=thresholds,
        source_hashes=source_hashes,
        empirical_precision=precision,
        sample_counts=counts,
        minimum_examples=min_examples,
        minimum_precision=min_precision,
    )


def load_profile(path):
    return Profile.model_validate_json(Path(path).expanduser().read_bytes())


def load_gold(case):
    case = Path(case)
    source = case / "preview.png"
    gold = PlanModel.model_validate_json((case / "gold.json").read_bytes())
    identity = hashlib.sha256(source.read_bytes()).hexdigest()
    metadata = case / "metadata.json"
    if (
        metadata.exists()
        and json.loads(metadata.read_text()).get("source_sha256") != identity
    ):
        raise ValueError(f"{case.name}: source hash does not match its snapshot")
    if not gold.walls or any(o.status == "proposed" for o in gold.openings):
        raise ValueError(
            f"{case.name}: finish reviewing the reference plan before calibration"
        )
    from PIL import Image

    with Image.open(source) as image:
        if image.size != (gold.image_transform.width, gold.image_transform.height):
            raise ValueError(
                f"{case.name}: source dimensions do not match reference geometry"
            )
    return source, gold, identity
