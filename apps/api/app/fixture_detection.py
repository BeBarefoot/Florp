"""Local, scale-aware matching of drawn floor-plan furniture symbols.

These are review candidates, not a classifier of arbitrary drawing styles.
Only synthetic symbol stencils are used; the blueprint never leaves the API.
"""
from dataclasses import dataclass
import math

import cv2
import numpy as np

# Dimensions of the drawn footprint, in metres. Width is across the front,
# depth runs from the back (top of the stencil) toward the front.
SIZES = {
    "bed": [(w, d) for w in (.86, .94, 1.02, 1.32, 1.48, 1.62, 1.8, 1.98)
            for d in (1.73, 1.9, 2.06, 2.22)],
    "wardrobe": [(w, d) for w in (1.25, 1.5, 1.73, 1.95, 2.2, 2.45, 2.7, 2.95, 3.2)
                 for d in (.49, .57, .65, .74)],
    "toilet": [(w, d) for w in (.35, .4, .45, .50) for d in (.49, .56, .63, .71)],
    "bathtub": [(w, d) for w in (.57, .64, .72, .8) for d in (1.45, 1.62, 1.8, 1.9, 1.96, 2.04)],
    "shower": [(w, d) for w in (.78, .9, 1.02, 1.14) for d in (.78, .9, 1.02, 1.14)],
}
HEIGHT = {"bed": .9, "wardrobe": 2.2, "toilet": .8, "bathtub": .56, "shower": 2}
MIN_SCORE = {"bed": .32, "wardrobe": .34, "toilet": .36, "bathtub": .29, "shower": .47}


@dataclass(frozen=True)
class Hit:
    kind: str
    score: float
    x: float
    y: float
    width: float
    depth: float
    rotation: int


def stencil(kind, w, h, variant=0):
    """Original, generated drafting strokes, independent of source drawings."""
    a = np.zeros((h, w), np.uint8)

    def xy(x, y):
        return round(x * (w-1)), round(y * (h-1))

    def line(*coords, weight=255):
        cv2.polylines(a, [np.array([xy(*p) for p in coords], np.int32)], False, weight, 1, cv2.LINE_AA)

    def rect(x, y, x2, y2, weight=255):
        cv2.rectangle(a, xy(x, y), xy(x2, y2), weight, 1, cv2.LINE_AA)

    def round_end(left, right, back, end, weight=255):
        # Straight sides and a half-ellipse nose.
        cap = min((right-left)*w*.5/h, (end-back)*.85)
        y = end-cap
        line((left, y), (left, back), (right, back), (right, y), weight=weight)
        arc = [(left+(right-left)*(1+math.cos(t))/2, y+cap*math.sin(t))
               for t in np.linspace(0, math.pi, 24)]
        line(*arc, weight=weight)

    if kind == "toilet":
        round_end(.05, .95, .04, .97)
        round_end(.20, .80, .20, .85)
        if variant:
            rect(.04, .03, .96, .24)
    elif kind == "bathtub":
        rect(.02, .01, .98, .99, 140)
        round_end(.08, .92, .035, .975)
        if variant:
            round_end(.17, .83, .09, .90, 160)
    elif kind == "bed":
        rect(.02, .015, .98, .985)
        if variant == 0:
            for x, end in ((.10, .45), (.54, .89)):
                rect(x, .09, end, .24, 175)
            line((.02,.30),(.97,.30),weight=165)
            line((.02,.62),(.97,.62),weight=170)
            line((.02,.84),(.97,.84))
            line((.80,.30),(.97,.51),(.80,.51),(.80,.30),weight=170)
        else:
            fold = ((.02,.27),(.22,.39),(.98,.22),(.02,.27))
            if variant == 2:
                fold = tuple((1-x,y) for x,y in fold)
            line(*fold,weight=250)
            line((.04,.15),(.20,.15),(.20,.86),(.04,.86),weight=130)
    elif kind == "wardrobe":
        rect(.02,.01,.98,.99)
        line((.01,.50),(.99,.50))
        for x in np.arange(.025, .99, (3.6 if not variant else 4.6)/w):
            line((x,.12),(x,.88),weight=185)
    else:
        rect(.02,.02,.98,.98,165)
        line((.10,.73),(.10,.88),(.25,.88))
        line((.16,.80),(.31,.63))
        if variant:
            line((.08,.06),(.92,.94),weight=190)
            line((.92,.06),(.08,.94),weight=190)
    return a


def evidence(kind, patch, variant):
    """Require local details which a wall edge or dimension line cannot supply."""
    h, w = patch.shape

    def sample(points, radius=1):
        values = []
        for x, y in points:
            x, y = round(x*(w-1)), round(y*(h-1))
            values.append(patch[max(0,y-radius):y+radius+1,max(0,x-radius):x+radius+1].max())
        return np.array(values)

    def straight(x1, y1, x2, y2):
        return sample(zip(np.linspace(x1,x2,10),np.linspace(y1,y2,10)))

    def cap(left, right, end):
        radius = min((right-left)*w*.5/h, end*.75)
        t = np.linspace(.24, np.pi-.24, 9)
        return sample(zip(left+(right-left)*(1+np.cos(t))/2,end-radius+radius*np.sin(t)))

    if kind == "toilet":
        outer, inner = cap(.05,.95,.97), cap(.20,.80,.85)
        left, right = straight(.06,.18,.06,.64), straight(.94,.18,.94,.64)
        return min(np.quantile(outer,.27), np.quantile(inner,.31), np.median(left), np.median(right)) >= 2.4
    if kind == "bathtub":
        nose=cap(.08,.92,.975)
        left,right=straight(.08,.12,.08,.72),straight(.92,.12,.92,.72)
        if min(np.quantile(nose,.25), np.quantile(left,.32),np.quantile(right,.32))<2:
            return False
        offset = min(.055,3.5/h)
        return np.mean(nose) >= 1.10 * np.mean(cap(.08,.92,.975-offset))
    if kind == "shower":
        # The inner diagonal drainage tick is required, not just the enclosure.
        tick=straight(.17,.78,.29,.65)
        return np.quantile(tick,.32)>=2.2 and np.quantile(straight(.10,.74,.10,.88),.35)>=1.5
    if kind == "wardrobe":
        # Cabinet shelving crosses the short axis many times. Stair steps or
        # a pair of long parallel dimension lines must not match by themselves.
        core=patch[round(h*.18):round(h*.82),round(w*.05):round(w*.95)]
        signal=np.quantile(core,.40,axis=0)
        peaks=(signal[1:-1]>1.9)&(signal[1:-1]>signal[:-2])&(signal[1:-1]>=signal[2:])
        return peaks.sum() >= max(5,w/9) and np.quantile(straight(.06,.05,.94,.05),.3)>1.6
    # A bed needs either a long folded-corner diagonal or an interior
    # transverse blanket line. Its outer rectangle alone is not a symbol.
    if variant:
        sign = 1 if variant == 1 else -1
        x = lambda f: f if sign == 1 else 1-f
        fold = straight(x(.23),.39,x(.94),.23)
        return np.quantile(fold,.30)>1.45 and np.quantile(straight(.10,.96,.91,.96),.33)>1.5
    blanket=straight(.13,.84,.86,.84)
    cross=straight(.12,.62,.87,.62)
    return np.quantile(blanket,.28)>.8 and np.median(cross)>1


def detect_fixtures(gray, mpp, obstacle=None, allowed=None):
    if gray.ndim != 2 or not math.isfinite(mpp) or mpp <= 0:
        return []
    # Bound each image and keep the stencil/image in the same physical units.
    step = min(64 * mpp, 1350 / max(gray.shape))
    ppm = step / mpp
    if ppm < 13:
        return []
    im = cv2.resize(gray, None, fx=step, fy=step, interpolation=cv2.INTER_AREA if step < 1 else cv2.INTER_CUBIC)
    f = im.astype(np.float32)
    stroke = np.maximum(cv2.GaussianBlur(f, (0,0), 2.4) - f, 0)
    stroke = cv2.GaussianBlur(np.minimum(stroke, 32), (0,0), .7)
    if stroke.max() < 2:
        return []
    integral = None
    if obstacle is not None:
        resized = cv2.resize(obstacle, (im.shape[1], im.shape[0]), interpolation=cv2.INTER_NEAREST)
        integral = cv2.integral(resized)
    hits = []
    for kind, sizes in SIZES.items():
        for width, depth in sizes:
            w, h = round(width*ppm), round(depth*ppm)
            if min(w,h) < 6:
                continue
            variants = (0,) if kind == "bathtub" or kind == "bed" and width >= 1.4 else range(3 if kind=="bed" else 2)
            for variant in variants:
                pattern = stencil(kind, w, h, variant)
                for rot in range(4):
                    t = np.ascontiguousarray(np.rot90(pattern, -rot)).astype(np.float32)
                    if any(a >= b for a,b in zip(t.shape, stroke.shape)):
                        continue
                    t = cv2.GaussianBlur(t,(0,0),.75)
                    res = cv2.matchTemplate(stroke, t, cv2.TM_CCOEFF_NORMED)
                    peak = cv2.dilate(res, np.ones((5,5),np.uint8))
                    ys,xs = np.where((res >= MIN_SCORE[kind]) & (res == peak))
                    if integral is not None and len(xs):
                        y1,x1=ys+t.shape[0],xs+t.shape[1]
                        occlusion=integral[y1,x1]-integral[ys,x1]-integral[y1,xs]+integral[ys,xs]
                        valid=occlusion<=(.21 if kind=="bathtub" else .13 if kind=="bed" else .09)*t.size
                        ys,xs=ys[valid],xs[valid]
                    if not len(xs):
                        continue
                    scores = res[ys,xs]
                    order = np.argsort(scores)
                    if kind in ("bathtub","bed"):
                        # A page full of strong dimension lines can otherwise
                        # starve the actual fixture in a quieter part of the plan.
                        bins = {}
                        local = []
                        cell = max(1,round(.65*ppm))
                        for j in order[::-1]:
                            key = xs[j]//cell,ys[j]//cell
                            if bins.get(key,0) < (3 if kind == "bathtub" else 1):
                                bins[key] = bins.get(key,0) + 1
                                local.append(j)
                        order = np.array(local[:210 if kind == "bathtub" else 85],dtype=np.intp)
                    else:
                        order = order[-24:]
                    for j in order:
                        x,y = xs[j],ys[j]
                        cx,cy = (x+t.shape[1]/2)/step, (y+t.shape[0]/2)/step
                        if allowed is not None and not allowed(kind,cx,cy,width,depth,rot*90,float(scores[j])):
                            continue
                        patch=stroke[y:y+t.shape[0],x:x+t.shape[1]]
                        score = float(scores[j])
                        if not evidence(kind,np.rot90(patch,rot),variant) and not (
                                kind == "bed" and not variant and width >= 1.4 and score >= .40):
                            continue
                        if kind == "wardrobe":
                            score += .055 * (width-1.25)
                        elif kind == "bed" and not variant and width >= 1.4:
                            score += .075
                        hits.append(Hit(kind,score,cx,cy,width,depth,rot*90))
    if obstacle is not None:
        toilets = [h for h in hits if h.kind == "toilet" and h.score >= .40]
        def supported_bath(h):
            if h.kind != "bathtub":
                return True
            for wc in toilets:
                distance = math.hypot(h.x-wc.x, h.y-wc.y)*mpp
                if not .60 <= distance <= 2:
                    continue
                # A tub candidate near a toilet on the same side of the
                # walls is more useful than an isolated rectangular vanity.
                x = np.rint(np.linspace(h.x,wc.x,20)).astype(int)
                y = np.rint(np.linspace(h.y,wc.y,20)).astype(int)
                if not obstacle[y,x].any():
                    return True
            return h.score >= .74
        hits = [h for h in hits if supported_bath(h)]
    return suppress(hits, mpp)


def suppress(hits, mpp):
    def box(h):
        w,d = (h.width,h.depth) if h.rotation%180==0 else (h.depth,h.width)
        return h.x-w/2/mpp,h.y-d/2/mpp,h.x+w/2/mpp,h.y+d/2/mpp
    def overlap(a,b):
        return max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    def area(a):
        return (a[2]-a[0])*(a[3]-a[1])
    found = []
    counts = {}
    priority = {"bed":.14,"wardrobe":.09,"toilet":.01,"bathtub":.01,"shower":0}
    for h in sorted(hits,key=lambda h: -(h.score+priority[h.kind])):
        if counts.get(h.kind,0) >= {"bed":5,"wardrobe":6,"toilet":5,"bathtub":3,"shower":4}[h.kind]:
            continue
        b = box(h)
        if any(overlap(b,a) / min(area(a),area(b)) > .34 for _,a in found):
            continue
        found.append((h,b))
        counts[h.kind] = counts.get(h.kind,0)+1
        if len(found) >= 24:
            break
    return [h for h,_ in found]


def for_plan(gray, model):
    """Use existing geometry as context, without requiring every room to close."""
    mpp = model.scale.meters_per_pixel
    if not mpp or not model.walls:
        return []
    obstacle = np.zeros(gray.shape, dtype=np.uint8)
    wall = np.zeros_like(obstacle)
    nodes = {n.id: n for n in model.nodes}

    def pt(p):
        return round(p.x), round(p.y)

    for w in model.walls:
        cv2.line(wall, pt(nodes[w.a]), pt(nodes[w.b]), 1, max(1, round(w.thickness_px*.75)))
    obstacle[:] = wall
    for stair in model.stairs:
        hull = cv2.convexHull(np.array([pt(p) for tread in stair.treads for p in tread], np.int32))
        cv2.fillConvexPoly(obstacle, hull, 1)
    if model.envelope:
        hull = np.array([pt(p) for p in model.envelope], np.int32)
    else:
        x,y,w,h = cv2.boundingRect(np.array([pt(n) for n in model.nodes], np.int32))
        hull = np.array([(x,y),(x+w-1,y),(x+w-1,y+h-1),(x,y+h-1)],np.int32)
    # Exclude dimension lines drawn outside the structural perimeter.
    outside = np.ones_like(wall)
    cv2.fillPoly(outside, [hull], 0)
    if not model.envelope:
        # An incompletely traced exterior wall must not clip an otherwise
        # supported object. Explicit user outlines remain authoritative.
        padding = max(1, min(101, round(.32/mpp)*2+1))
        outside = cv2.erode(outside, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (padding,padding)))
    obstacle |= outside

    room_labels = np.zeros(gray.shape, dtype=np.int32)
    regions = [*model.rooms, *model.room_zones]
    for i, room in enumerate(regions, 1):
        cv2.fillPoly(room_labels, [np.array([pt(p) for p in room.polygon], np.int32)], i)
    distance = cv2.distanceTransform(1-wall, cv2.DIST_L2, 5)*mpp

    def allowed(kind, cx, cy, w, d, rotation, score):
        x,y = round(cx),round(cy)
        if not (0 <= x < gray.shape[1] and 0 <= y < gray.shape[0]) or obstacle[y,x]:
            return False
        i = room_labels[y,x]
        if i:
            room = regions[i-1]
            if room.room_type == "corridor":
                return False
            if kind in ("shower","toilet","bathtub") and room.room_type in ("bedroom","kitchen"):
                return False
            if kind in ("bed","wardrobe") and (room.room_type == "bathroom" or
                    room.room_type is None and 0 < getattr(room,"area_px2",0)*mpp*mpp < 4.5):
                return False
        angle=rotation*math.pi/180
        corners=[]
        # Require a nearby architectural wall, favouring the back of
        # a toilet/bed and the back edge of built-in wardrobes.
        offsets = [(0,-d/2)]
        if kind in ("bathtub","shower"):
            offsets += [(0,d/2),(-w/2,0),(w/2,0)]
        for u,v in offsets:
            xx,yy=round(cx+(u*math.cos(angle)-v*math.sin(angle))/mpp), round(cy+(u*math.sin(angle)+v*math.cos(angle))/mpp)
            if 0 <= yy < gray.shape[0] and 0 <= xx < gray.shape[1]:
                corners.append(distance[yy,xx])
        if kind == "bed" and score >= .53:
            return True
        if kind == "bathtub":
            return len(corners)==4 and min(corners[:2]) <= .36 and min(corners[2:]) <= .26
        return bool(corners) and min(corners) <= {"wardrobe":.23,"toilet":.34,"bed":.40,"shower":.30}[kind]

    return detect_fixtures(gray, mpp, obstacle, allowed)
