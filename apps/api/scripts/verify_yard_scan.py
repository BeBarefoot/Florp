"""Verify extraction landmarks on the original private yard PNG.

From apps/api run: python -m scripts.verify_yard_scan /path/to/yard.png
The reference photographs and generated PlanModels stay outside source control.
"""

import argparse
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

import cv2
from numpy import hypot
from app.workspace_worker import build

# Source-image pixels. Each repeated fixture and each door is checked separately.
OBJECTS = [
    ("cooktop", 688, 83),
    ("sink", 778, 86),
    ("cabinets", 774, 84),
    ("cabinets", 912, 143),
    ("bar_counter", 738, 203),
    ("bar_stools", 738, 181),
    ("sofa", 520, 316),
    ("coffee_table", 412, 319),
    ("tv_console", 277, 309),
    ("dining_table", 414, 127),
    ("patio_set", 163, 270),
    ("toilet", 697, 370),
    ("sink", 685, 325),
    ("tree", 55, 31),
    ("tree", 1065, 169),
    ("car", 881, 317),
]
APERTURES = [
    ("door", (570, 59), (629, 59)),
    ("door", (943, 63), (990, 63)),
    ("door", (732, 237), (732, 278)),
    ("door", (685, 281), (725, 281)),
    ("window", (282, 59), (366, 59)),
    ("window", (430, 60), (546, 60)),
    ("window", (709, 60), (840, 60)),
    ("window", (256, 75), (256, 233)),
]


def check(source):
    if (
        sha256(source.read_bytes()).hexdigest()
        != "764b243c8a44882502e68c47621a8688c0249c45c114e5860f5d1bd32e436485"
    ):
        raise ValueError("Supply the original yard PNG from the October 24 archive.")
    with TemporaryDirectory() as tmp:
        original = cv2.imread(str(source))
        for factor in (1.0, 0.8, 1.25):
            path = source
            if factor != 1:
                path = Path(tmp) / "resized.png"
                cv2.imwrite(
                    str(path),
                    cv2.resize(
                        original,
                        None,
                        fx=factor,
                        fy=factor,
                        interpolation=cv2.INTER_AREA if factor < 1 else cv2.INTER_CUBIC,
                    ),
                )
            check_landmarks(build(str(path), plan_id="yard-verification"), factor)


def check_landmarks(model, factor):
    errors = []
    missed = [
        (kind, x, y)
        for kind, x, y in OBJECTS
        if not any(
            s.kind == kind
            and hypot(s.position.x / factor - x, s.position.y / factor - y) <= 15
            for s in model.room_symbols
        )
    ]
    errors.extend(f"Missing {kind} near ({x}, {y})" for kind, x, y in missed)

    def near(p, xy):
        return hypot(p.x / factor - xy[0], p.y / factor - xy[1]) <= 10

    for kind, a, b in APERTURES:
        if not any(
            o.kind == kind
            and o.span
            and any(near(p, a) and near(q, b) for p, q in (o.span, o.span[::-1]))
            for o in model.openings
        ):
            errors.append(f"Missing {kind} between {a} and {b}")
    if len(model.openings) != len(APERTURES):
        errors.append(f"Expected {len(APERTURES)} openings, got {len(model.openings)}")
    if len(model.room_symbols) != len(OBJECTS):
        errors.append(
            f"Expected {len(OBJECTS)} object marks, got {len(model.room_symbols)}"
        )
    if {r.label for r in model.rooms} != {"Kitchen & living room", "Bathroom"} or len(
        model.rooms
    ) != 2:
        errors.append("Indoor room boundaries or labels changed")
    if errors:
        raise SystemExit("\n".join(errors))
    print(
        f"{factor:g}x: {len(OBJECTS) - len(missed)}/{len(OBJECTS)} object landmarks matched, "
        f"{len(model.room_symbols)} marks returned, {len(APERTURES)} openings and two rooms verified."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    cv2.setNumThreads(2)
    check(parser.parse_args().source)
