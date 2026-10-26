"""Normalize mask-derived axes before creating 3D wall solids.

Merge near-coincident, overlapping wall runs in source pixel coordinates.
Do NOT bridge genuine openings: merge only overlapping or tiny (<4px) gaps.
Keep perpendicular intersections as separate wall edges for later topology.
"""
from __future__ import annotations
from math import hypot
from .wall_segmentation import MaskLine, WallMaskReport

def consolidate_wall_runs(report:WallMaskReport,axis_tolerance:float=5.,
                          gap_tolerance:float=3.)->WallMaskReport:
    if axis_tolerance<0 or gap_tolerance<0:raise ValueError('Invalid axis tolerances')
    horizontal=[]
    vertical=[]
    for line in report.lines:
        dx=line.x2-line.x1;dy=line.y2-line.y1
        if hypot(dx,dy)<2:continue
        if abs(dy)<=max(2.,abs(dx)*.09):
            horizontal.append((round((line.y1+line.y2)/2,3),
                               min(line.x1,line.x2),max(line.x1,line.x2),line.support))
        elif abs(dx)<=max(2.,abs(dy)*.09):
            vertical.append((round((line.x1+line.x2)/2,3),
                             min(line.y1,line.y2),max(line.y1,line.y2),line.support))
        # Diagonal masks stay in the pixel overlay until we support angled walls.
    merged=[]
    for is_horizontal,items in ((True,horizontal),(False,vertical)):
        # Longest first anchors the representative axis to structural walls
        # instead of moving an entire wall to a tiny furniture-like stroke.
        items.sort(key=lambda p:(-(p[2]-p[1]),p[0],p[1]))
        clusters=[]
        for coord,begin,end,support in items:
            choices=[c for c in clusters if abs(coord-c['axis'])<=axis_tolerance
                     and begin<=c['end']+gap_tolerance and end>=c['begin']-gap_tolerance]
            if choices:
                target=min(choices,key=lambda c:abs(coord-c['axis']))
                target['begin']=min(target['begin'],begin)
                target['end']=max(target['end'],end)
                target['support']=max(target['support'],support)
                # Do not average axes: moving them breaks mask/junction alignment.
            else:
                clusters.append(dict(axis=coord,begin=begin,end=end,support=support))
        # Clusters can become connected by later items: union transitively
        # only if they share an axis and nearly touch, never across an opening.
        changed=True
        while changed:
            changed=False
            for i in range(len(clusters)):
                for j in range(i+1,len(clusters)):
                    a,b=clusters[i],clusters[j]
                    if abs(a['axis']-b['axis'])<=axis_tolerance and (
                        a['begin']<=b['end']+gap_tolerance and
                        b['begin']<=a['end']+gap_tolerance):
                        # Prefer representative axis of longer run.
                        if b['end']-b['begin']>a['end']-a['begin']:
                            a['axis']=b['axis']
                        a['begin']=min(a['begin'],b['begin'])
                        a['end']=max(a['end'],b['end'])
                        a['support']=max(a['support'],b['support'])
                        clusters.pop(j)
                        changed=True
                        break
                if changed:break
        for c in clusters:
            a,b=c['begin'],c['end'];axis=c['axis']
            if is_horizontal:
                merged.append(MaskLine(x1=a,y1=axis,x2=b,y2=axis,support=c['support']))
            else:
                merged.append(MaskLine(x1=axis,y1=a,x2=axis,y2=b,support=c['support']))
    merged.sort(key=lambda l:(min(l.y1,l.y2),min(l.x1,l.x2),l.y2,l.x2))
    return report.model_copy(update={'lines':merged,'line_count':len(merged),
        'warning':report.warning+' Collinear runs consolidated; unsupported gaps remain open.'})
