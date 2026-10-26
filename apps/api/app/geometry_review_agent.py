"""Conservative, deterministic geometry review assistant.

Never writes a layout or invents training labels. Prioritizes unsupported
Yytsi-only wall evidence and checks candidate gaps against the actual mask.
Scores are *heuristic ranks*, not calibrated probabilities.
"""
from __future__ import annotations
from math import hypot
import numpy as np
from pydantic import BaseModel, Field
from .geometry import Geometry, Pt
from .evidence_fusion import FusedCandidate, _support, _same_axis, _overlap_fraction
from .missing_wall_evidence import _distance

class ReviewSuggestion(BaseModel):
    candidate_id: str
    reason: str
    category: str
    priority: float = Field(ge=0,le=1)
    mask_support: float = Field(ge=0,le=1)
    connects_to_structure: bool
    start: Pt
    end: Pt

def _connected(point: Pt, walls, tolerance:float)->bool:
    return any(_distance(point,w.start,w.end)<=tolerance for w in walls)

def review_geometry(
    proposal:Geometry,candidates:list[FusedCandidate],mask:np.ndarray,
    *,max_items:int=16,min_support:float=.78,
)->list[ReviewSuggestion]:
    """Rank existing, evidence-backed wall candidates for human review.

    No novel line is synthesized here. Input candidates come from the same
    extracted raster, so reviewing one can use the existing fusion audit flow.
    """
    if mask.shape!=(proposal.height_px,proposal.width_px):
        raise ValueError('Review mask dimensions differ from blueprint')
    if not 0<=min_support<=1 or max_items<1 or max_items>100:
        raise ValueError('Invalid review configuration')
    proposals=[]
    reference_walls=[w for w in proposal.walls
                     if not (w.id.startswith('w') and w.id[1:].isdigit())]
    for item in candidates:
        if item.category!='yytsi_only':continue
        length=hypot(item.end.x-item.start.x,item.end.y-item.start.y)
        if length<max(18,min(proposal.width_px,proposal.height_px)*.035):continue
        support=_support(mask,item.start,item.end)
        if support<min_support:continue
        # A span already covered by the proposed structural model does not
        # need additional review, even if a detector labelled it differently.
        if any(_same_axis(item.start,item.end,w.start,w.end,6) and
               _overlap_fraction(item.start,item.end,w.start,w.end)>.75
               for w in reference_walls):
            continue
        ends=int(_connected(item.start,reference_walls,12))+int(
            _connected(item.end,reference_walls,12))
        # Free-floating strokes can be text/furniture. Do not promote to
        # high priority or claim they are a missing wall.
        if ends==0:continue
        priority=min(1.,.35+.35*support+.12*ends+
                     .10*min(1,length/max(40,min(mask.shape)*.3)))
        reason=('Connects two existing wall regions' if ends==2 else
                'Touches an existing wall; other endpoint requires review')
        proposals.append(ReviewSuggestion(candidate_id=item.id,
            reason=reason+'; source segmentation supports this span',
            category='possible_missing_partition',priority=round(priority,3),
            mask_support=round(support,3),connects_to_structure=True,
            start=item.start,end=item.end))
    proposals.sort(key=lambda p:(-p.priority,p.candidate_id))
    return proposals[:max_items]
