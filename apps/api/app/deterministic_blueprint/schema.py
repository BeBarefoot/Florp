from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Point = tuple[float, float]


class CalibrationReference(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    # Coordinates in the EXIF-oriented original image, before any resize/warp.
    start: Point
    end: Point
    length_cm: float = Field(gt=0, le=100000)

    @model_validator(mode="after")
    def nonzero(self):
        if self.start == self.end:
            raise ValueError("Calibration endpoints must be different")
        return self


class Options(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    mode: Literal["all_walls", "outer_walls"] = "all_walls"
    reference: CalibrationReference | None = None
    default_scale_px_per_cm: float | None = Field(default=None, ge=0.02, le=100)
    ocr: bool = True
    ocr_languages: str = Field(default="eng+heb", pattern=r"^[a-z+_]+$", max_length=80)
    ocr_timeout_s: float = Field(default=1.5, ge=0.05, le=5)
    document_corners: list[Point] | None = Field(
        default=None, min_length=4, max_length=4
    )
    page_aspect_ratio: float | None = Field(default=None, ge=0.1, le=10)
    max_processing_side: int = Field(default=2400, ge=512, le=4000)
    min_component_cm2: float = Field(default=30, ge=1, le=500)
    min_thickness_cm: float = Field(default=4, ge=1, le=30)
    close_kernel_px: Literal[3, 5, 7] = 5
    simplify_cm: float = Field(default=1.5, ge=0, le=3)
    snap_degrees: float = Field(default=5, ge=0, le=5)
    # Bridge only for perimeter *classification*. Never added to exported walls.
    envelope_gap_cm: float = Field(default=180, ge=0, le=250)
    exterior_band_cm: float = Field(default=40, ge=10, le=80)
    print_scale: float = Field(default=100, ge=10, le=1000)
    red_saturation_min: int = Field(default=40, ge=20, le=255)
    blue_saturation_min: int = Field(default=60, ge=20, le=255)
    # Optional source-coordinate polygon restricts extraction to architecture,
    # excluding colored site boundaries / other plans on the same sheet.
    architecture_roi: list[Point] | None = Field(
        default=None, min_length=3, max_length=100
    )


class ExtractionError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
