"""Scale decision based on multiple independent, agreeing dimension observations."""
from __future__ import annotations
from pydantic import BaseModel, Field
from statistics import median
from .measurements import ScaleSuggestion

class ScaleEstimate(BaseModel):
    px_per_meter: float
    confidence: float=Field(ge=0,le=1)
    status: str
    supporting_labels: list[str]
    evidence_count: int

def automatic_scale(suggestions:list[ScaleSuggestion])->ScaleEstimate|None:
    # The paired-line detector is a weak signal. Never assume a scale from one
    # OCR label or nearby piece of unrelated drawing geometry.
    if len(suggestions)<3:return None
    values=sorted(suggestions,key=lambda s:s.px_per_meter)
    groups=[]
    for candidate in values:
        related=[s for s in values if abs(s.px_per_meter-candidate.px_per_meter)/candidate.px_per_meter<=.055]
        # Require three distinct recognized dimension labels, not repeated OCR
        # over a single line or unrelated duplicates from the same annotation.
        distinct={(s.text,round(s.line['x1']/10),round(s.line['y1']/10)) for s in related}
        if len(distinct)>=3:groups.append(related)
    if not groups:return None
    best=max(groups,key=lambda group:(len(group),sum(s.confidence for s in group)))
    ppm=median([x.px_per_meter for x in best])
    dispersion=max(abs(x.px_per_meter-ppm)/ppm for x in best)
    # Still provisional: native PDF vector/text association is not semantically
    # verified. A high numeric agreement cannot prove labels are dimensions.
    confidence=round(min(.79,.45+len(best)*.045-dispersion),2)
    return ScaleEstimate(px_per_meter=round(ppm,4),confidence=confidence,
      status='provisional_auto',supporting_labels=[s.text for s in best],
      evidence_count=len(best))
