"""Source-pixel reconstruction from reviewed masks, with explicit unresolved evidence.

Only annotated footprint overlap can extend junctions. Opening masks can bridge
collinear host runs; general blank gaps are never filled to improve a counter.
"""
from math import hypot
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union
from .geometry import Geometry,Wall,Pt,Opening,Room
from .graph_adapter import from_geometry,to_geometry

def reconstruct(objects,width,height,ppm=None):
    walls=[];shapes={};thickness={};issues=[]
    for i,obj in enumerate(objects):
        if obj['kind']!='wall':continue
        poly=Polygon(obj['polygon']);r=list(poly.minimum_rotated_rectangle.exterior.coords)[:4]
        lengths=[hypot(r[(j+1)%4][0]-r[j][0],r[(j+1)%4][1]-r[j][1]) for j in range(4)]
        j=min(range(4),key=lambda k:lengths[k]);k=(j+2)%4
        mid=lambda n:Pt(x=(r[n][0]+r[(n+1)%4][0])/2,y=(r[n][1]+r[(n+1)%4][1])/2)
        a,b=mid(j),mid(k)
        if hypot(a.x-b.x,a.y-b.y)<3:issues.append({'kind':'short_wall','object':i});continue
        wid=f'mask-{i}';walls.append(Wall(id=wid,start=a,end=b,thickness_m=min(2,max(.01,lengths[j]/ppm)) if ppm else .15))
        shapes[wid]=poly;thickness[wid]=lengths[j]
        if poly.area/poly.minimum_rotated_rectangle.area<.75:issues.append({'kind':'complex_wall_mask','object':i,'message':'Split bent or concave wall footprints into straight runs.'})
    if any(issue['kind']=='complex_wall_mask' for issue in issues):
        # Connected L/T footprints cannot be represented by a rotated bounding box.
        # Reuse the tested mask topology decoder in the original pixel frame.
        import cv2,numpy as np
        from .mask_topology import region_wall_lines
        from .wall_run_normalization import consolidate_wall_runs
        raster=np.zeros((height,width),dtype=np.uint8)
        all_shapes=[]
        for obj in objects:
            if obj['kind']=='wall':
                cv2.fillPoly(raster,[np.rint(obj['polygon']).astype(np.int32)],255)
                all_shapes.append(Polygon(obj['polygon']))
        footprint=unary_union(all_shapes)
        runs=consolidate_wall_runs(region_wall_lines(raster,min_length=8))
        if runs.lines:
            walls=[];shapes={};thickness={}
            for i,line in enumerate(runs.lines):
                wid=f'run-{i}';a=Pt(x=line.x1,y=line.y1);b=Pt(x=line.x2,y=line.y2)
                mid=Point((a.x+b.x)/2,(a.y+b.y)/2)
                thick=max(1.,2*footprint.boundary.distance(mid))
                walls.append(Wall(id=wid,start=a,end=b,thickness_m=min(2,max(.01,thick/ppm)) if ppm else .15))
                shapes[wid]=footprint.intersection(LineString([(a.x,a.y),(b.x,b.y)]).buffer(thick))
                thickness[wid]=thick
    def extended(w):
        dx=w.end.x-w.start.x;dy=w.end.y-w.start.y;l=hypot(dx,dy);pad=thickness[w.id]
        return LineString([(w.start.x-dx/l*pad,w.start.y-dy/l*pad),(w.end.x+dx/l*pad,w.end.y+dy/l*pad)])
    for i,a in enumerate(walls):
        for b in walls[i+1:]:
            if shapes[a.id].distance(shapes[b.id])>1:continue
            p=extended(a).intersection(extended(b))
            if p.geom_type!='Point':continue
            for w in (a,b):
                endpoint=min(('start','end'),key=lambda k:hypot(getattr(w,k).x-p.x,getattr(w,k).y-p.y))
                old=getattr(w,endpoint)
                if hypot(old.x-p.x,old.y-p.y)<=thickness[w.id] and unary_union([shapes[a.id],shapes[b.id]]).buffer(1).covers(LineString([(old.x,old.y),(p.x,p.y)])):
                    setattr(w,endpoint,Pt(x=p.x,y=p.y))
    # Bridge only explicit opening evidence between compatible straight host runs.
    openings=[(i,Polygon(o['polygon']),o['kind']) for i,o in enumerate(objects) if o['kind']!='wall']
    for _,poly,_ in openings:
        pairs=[]
        for i,a in enumerate(walls):
            for b in walls[i+1:]:
                ax=a.end.x-a.start.x;ay=a.end.y-a.start.y;al=hypot(ax,ay)
                bx=b.end.x-b.start.x;by=b.end.y-b.start.y;bl=hypot(bx,by)
                if abs(ax*by-ay*bx)/(al*bl)>.02:continue
                pts=[a.start,a.end,b.start,b.end]
                near=min(((x,y) for x in pts[:2] for y in pts[2:]),key=lambda v:hypot(v[0].x-v[1].x,v[0].y-v[1].y))
                gap=LineString([(near[0].x,near[0].y),(near[1].x,near[1].y)])
                if gap.length<1 or not poly.buffer(1).covers(gap):continue
                if abs(ax*(b.start.y-a.start.y)-ay*(b.start.x-a.start.x))/al>1:continue
                pairs.append((a,b,pts))
        if len(pairs)==1:
            a,b,pts=pairs[0];x,y=max(((x,y) for x in pts for y in pts),key=lambda v:hypot(v[0].x-v[1].x,v[0].y-v[1].y))
            a.start=x.model_copy();a.end=y.model_copy();walls.remove(b)
    anchored=[];pixel_openings=[]
    for i,poly,kind in openings:
        candidates=[]
        for wall in walls:
            line=LineString([(wall.start.x,wall.start.y),(wall.end.x,wall.end.y)])
            if line.distance(poly.centroid)>max(thickness[wall.id],1):continue
            spans=[line.project(Point(p)) for p in poly.exterior.coords]
            lo,hi=min(spans),max(spans)
            if hi-lo<1:continue
            candidates.append((wall,lo,hi))
        if len(candidates)!=1:
            issues.append({'kind':'opening_host','object':i,'message':'Choose/split a host footprint; ambiguous or missing wall.'});continue
        wall,lo,hi=candidates[0];pixel_openings.append({'object':i,'wall_id':wall.id,'offset_px':lo,'width_px':hi-lo,'kind':kind})
        if ppm:anchored.append(Opening(id=f'mask-{i}',kind=kind,wall_id=wall.id,offset_m=lo/ppm,width_m=(hi-lo)/ppm,height_m=2.1 if kind=='door' else 1.2,sill_m=0 if kind=='door' else .9))
    g=Geometry(width_px=width,height_px=height,px_per_meter=ppm,scale_source='user_confirmed' if ppm else 'unknown',walls=walls,openings=anchored)
    plan=from_geometry(g)
    for pending in plan.pending_openings:
        issues.append({'kind':'opening_span_crosses_junction','object':int(pending.id.split('-')[-1]),'message':'Opening spans multiple host edges; inspect the source and split/correct the footprint.'})
    # Room cycles are hypotheses; metric preview never silently verifies them.
    projected=to_geometry(plan,include_derived_rooms=True,draft_preview=True)
    from .inspection_issues import regional_issues
    regions,suppressed=regional_issues(issues,objects)
    return {'geometry':projected.model_dump(mode='json'),'pixel_openings':pixel_openings,'issues':regions,'suppressed_noise_count':suppressed,'canonical_plan':plan.model_dump(mode='json')}
