"""Source-supported, whole-graph reconstruction with explicit review.

A bounded deterministic hypothesis search, not an architectural truth oracle.
Only adds evidenced continuations/corners. It does not move existing junctions,
change opening anchors, infer scale or certify polygonized rooms.
"""
from __future__ import annotations
from collections import Counter
from hashlib import sha256
from itertools import combinations
import json
from math import hypot, ceil
from PIL import Image
from .geometry import Pt
from .plan_graph import CanonicalPlan, PlanNode, PlanWall
from .graph_adapter import derive_faces
from .graph_operations import _check_intersections
from .graph_validation import require_valid


def topology(plan: CanonicalPlan) -> dict:
    adjacency={n.id:set() for n in plan.nodes}
    for w in plan.walls:
        adjacency[w.start_node_id].add(w.end_node_id)
        adjacency[w.end_node_id].add(w.start_node_id)
    unseen={n for n,edges in adjacency.items() if edges}
    components=0
    while unseen:
        stack=[min(unseen)];components+=1
        while stack:
            node=stack.pop()
            if node not in unseen:continue
            unseen.remove(node);stack.extend(adjacency[node])
    return {'components':components,'dangling':sum(len(v)==1 for v in adjacency.values()),
            'faces':len(plan.rooms),'walls':len(plan.walls)}


def _support(image: Image.Image, points: list[Pt]) -> float:
    """Fraction of interior line samples with dark pixels within one pixel.

    Endpoint ink is excluded so two existing end caps cannot support a gap.
    This is deliberately evidence, not calibrated model confidence.
    """
    scores=[]
    for a,b in zip(points,points[1:]):
        length=hypot(b.x-a.x,b.y-a.y)
        if length<6:return 0.
        samples=[]
        for i in range(2,ceil(length)-1):
            t=i/length
            x,y=round(a.x+(b.x-a.x)*t),round(a.y+(b.y-a.y)*t)
            samples.append(any(image.getpixel((xx,yy))<128
                for xx in range(max(0,x-1),min(image.width,x+2))
                for yy in range(max(0,y-1),min(image.height,y+2))))
        scores.append(sum(samples)/len(samples) if samples else 0.)
    return min(scores,default=0.)


def apply_candidates(source: CanonicalPlan, candidates: list[dict]) -> CanonicalPlan:
    """Apply compatible hypotheses atomically without touching existing objects."""
    result=source.model_copy(deep=True)
    added=set()
    by_node={n.id:n for n in result.nodes}
    by_wall={w.id:w for w in result.walls}
    for item in candidates:
        ids=[item['start_node_id']]
        points=[Pt.model_validate(p) for p in item['points']]
        if len(points)==3:
            nid='reconstruction-node-'+item['id']
            if nid in by_node:raise ValueError('Duplicate reconstruction junction')
            node=PlanNode(id=nid,point=points[1],evidence_ids=[item['id']])
            result.nodes.append(node);by_node[nid]=node;ids.append(nid)
        ids.append(item['end_node_id'])
        parent=by_wall[item['source_wall_ids'][0]]
        for i,(start,end) in enumerate(zip(ids,ids[1:])):
            wid='reconstruction-wall-'+item['id']+'-'+str(i)
            if wid in by_wall:raise ValueError('Duplicate reconstruction wall')
            result.walls.append(PlanWall(id=wid,start_node_id=start,end_node_id=end,
                thickness_m=parent.thickness_m,height_m=parent.height_m,
                inferred=True,evidence_ids=item['source_wall_ids']+[item['id']]))
            added.add(wid)
    require_valid(result)
    _check_intersections(result,added)
    derived=derive_faces(result)
    # Do not silently invalidate a confirmed face by introducing a partition.
    derived_by_id={r.id:r for r in derived}
    for room in source.rooms:
        if room.verified and room.id not in derived_by_id:
            raise ValueError('Proposal would change a verified room boundary')
        if room.id in derived_by_id:
            derived_by_id[room.id]=room.model_copy(deep=True)
    result.rooms=sorted(derived_by_id.values(),key=lambda r:r.id)
    require_valid(result)
    return result


def propose_reconstruction(source: CanonicalPlan, image: Image.Image,
                           max_gap_px: float=80, min_support: float=.8) -> dict:
    require_valid(source)
    if not 6<=max_gap_px<=200:raise ValueError('max_gap_px must be between 6 and 200')
    if not .5<=min_support<=1:raise ValueError('min_support must be between .5 and 1')
    if image.size!=(source.width_px,source.height_px):raise ValueError('Source image dimensions differ from graph')
    image=image.convert('L')
    nodes={n.id:n.point for n in source.nodes}
    incidence={n:[] for n in nodes}
    for w in source.walls:
        incidence[w.start_node_id].append(w);incidence[w.end_node_id].append(w)
    tips=sorted(n for n,walls in incidence.items() if len(walls)==1)
    if len(tips)>300:raise ValueError('Too many dangling junctions; review graph before reconstruction')
    candidates=[];rejected=Counter()
    def direction(n):
        w=incidence[n][0];other=w.end_node_id if w.start_node_id==n else w.start_node_id
        p,q=nodes[n],nodes[other];length=hypot(p.x-q.x,p.y-q.y)
        return ((p.x-q.x)/length,(p.y-q.y)/length)
    for a,b in combinations(tips,2):
        p,q=nodes[a],nodes[b]
        distance=hypot(p.x-q.x,p.y-q.y)
        if not 6<=distance<=max_gap_px:continue
        u,v=direction(a),direction(b)
        paths=[]
        dx,dy=(q.x-p.x)/distance,(q.y-p.y)/distance
        # Collinear continuation: both dangling ends must face the gap.
        if u[0]*dx+u[1]*dy>.995 and v[0]*(-dx)+v[1]*(-dy)>.995:
            paths.append(('continuation',[p,q]))
        # Perpendicular outward rays meet at a supported architectural corner.
        cross=u[0]*v[1]-u[1]*v[0]
        if abs(u[0]*v[0]+u[1]*v[1])<.05 and abs(cross)>.01:
            delta=(q.x-p.x,q.y-p.y)
            t=(delta[0]*v[1]-delta[1]*v[0])/cross
            s=(delta[0]*u[1]-delta[1]*u[0])/cross
            if t>=6 and s>=6 and t+s<=max_gap_px:
                corner=Pt(x=p.x+t*u[0],y=p.y+t*u[1])
                if 0<=corner.x<=source.width_px and 0<=corner.y<=source.height_px:
                    paths.append(('corner',[p,corner,q]))
        for kind,points in paths:
            support=_support(image,points)
            if support<min_support:
                rejected['insufficient_raster_support']+=1;continue
            raw={'kind':kind,'start_node_id':a,'end_node_id':b,
                 'points':[pt.model_dump() for pt in points],
                 'source_wall_ids':sorted({incidence[a][0].id,incidence[b][0].id})}
            cid=sha256(json.dumps(raw,sort_keys=True).encode()).hexdigest()[:20]
            item={**raw,'id':cid,'raster_support':round(support,6),
                  'length_px':sum(hypot(y.x-x.x,y.y-x.y) for x,y in zip(points,points[1:]))}
            try:
                proposed=apply_candidates(source,[item])
            except ValueError:
                rejected['structural_conflict']+=1;continue
            item['after']=topology(proposed)
            candidates.append(item)
    before=topology(source)
    candidates.sort(key=lambda c:(-(before['components']-c['after']['components']),
        -(c['after']['faces']-before['faces']),-c['raster_support'],c['kind']!='continuation',c['length_px'],c['id']))
    compatible=[];used=set();current=source
    for item in candidates:
        if used & {item['start_node_id'],item['end_node_id']}:
            item['recommended']=False;item['reason']='Competes for an already selected dangling junction';continue
        try:
            trial=apply_candidates(current,[item])
        except ValueError:
            item['recommended']=False;item['reason']='Conflicts with the selected global proposal';continue
        item['recommended']=True;item['reason']='Raster-supported repair, compatible with the whole selected graph'
        compatible.append(item);current=trial;used.update((item['start_node_id'],item['end_node_id']))
    return {'candidates':candidates,'before':before,'after':topology(current),
            'recommended_ids':[c['id'] for c in compatible], 'rejected':dict(sorted(rejected.items())),
            'warning':'Raster ink may be text or furniture. Review every proposed wall. Faces remain unverified; unresolved gaps remain open.'}
