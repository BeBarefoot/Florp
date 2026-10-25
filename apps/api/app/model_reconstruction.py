"""Convert long wall detection boxes into conservative, unverified wall centerlines."""
from math import hypot
from .geometry import Geometry,Wall,Pt,Opening
from .pretrained_detector import DetectorResult

def _projection(x,y,w):
    dx=w.end.x-w.start.x;dy=w.end.y-w.start.y
    length=dx*dx+dy*dy
    t=max(0,min(1,((x-w.start.x)*dx+(y-w.start.y)*dy)/length)) if length else 0
    return hypot(x-w.start.x-dx*t,y-w.start.y-dy*t),t

def _model_wall_candidates(result:DetectorResult):
    """Two-pass box conversion: strong elongated walls first, short continuations second.

    Weak candidates must be nearly collinear AND touch a strong wall endpoint.
    A standalone short stroke is not evidence of an architectural wall.
    """
    strong=[]
    weak=[]
    dropped={'below_confidence':0,'too_short':0,'not_elongated':0,'duplicate':0}
    threshold=max(22,min(result.image_width,result.image_height)*.075)
    for i,box in enumerate(result.boxes):
        if box.category!='wall':continue
        if box.confidence<.35:
            dropped['below_confidence']+=1;continue
        bw=box.x2-box.x1;bh=box.y2-box.y1
        length=max(bw,bh)
        if length/max(1,min(bw,bh))<2.3:
            dropped['not_elongated']+=1;continue
        if length<max(12,threshold*.35):
            dropped['too_short']+=1;continue
        if bw>=bh:
            y=(box.y1+box.y2)/2
            a=Pt(x=box.x1,y=y);b=Pt(x=box.x2,y=y)
        else:
            x=(box.x1+box.x2)/2
            a=Pt(x=x,y=box.y1);b=Pt(x=x,y=box.y2)
        entry=(i,a,b)
        (strong if length>=threshold else weak).append(entry)
    result_walls=list(strong)
    for i,a,b in weak:
        direction='horizontal' if abs(b.x-a.x)>=abs(b.y-a.y) else 'vertical'
        # Max 14 pixels gap to a trusted collinear end; no free-floating scraps.
        def connected(item):
            _,c,d=item
            same=(abs(d.y-c.y)<1 if direction=='horizontal' else abs(d.x-c.x)<1)
            offset=abs(a.y-c.y) if direction=='horizontal' else abs(a.x-c.x)
            if not same or offset>max(6,min(result.image_width,result.image_height)*.018):return False
            return min(hypot(a.x-q.x,a.y-q.y) for q in (c,d))<=14 or min(
                hypot(b.x-q.x,b.y-q.y) for q in (c,d))<=14
        if any(connected(w) for w in strong):
            result_walls.append((i,a,b))
        else:dropped['too_short']+=1
    unique=[]
    for item in result_walls:
        _,a,b=item
        if any(hypot(a.x-c.x,a.y-c.y)<7 and hypot(b.x-d.x,b.y-d.y)<7 for _,c,d in unique):
            dropped['duplicate']+=1;continue
        unique.append(item)
    return unique,dropped

def reconstruct(result:DetectorResult, base:Geometry)->Geometry:
    if (result.image_width,result.image_height)!=(base.width_px,base.height_px):
        raise ValueError('Image dimensions mismatch')
    candidates,_=_model_wall_candidates(result)
    walls=[Wall(id='model-'+str(i),start=a,end=b,inferred=True) for i,a,b in candidates]
    if not walls:raise ValueError('Pretrained detector returned no suitable elongated wall boxes')
    scale=base.px_per_meter or 60.
    openings=[]
    for i,box in enumerate(result.boxes):
        if box.category not in ('door','window') or box.confidence<.35:continue
        x=(box.x1+box.x2)/2;y=(box.y1+box.y2)/2
        matches=[(*_projection(x,y,w),index) for index,w in enumerate(walls)]
        distance,t,index=min(matches)
        if distance>max(16,min(base.width_px,base.height_px)*.06):continue
        w=walls[index]
        length=hypot(w.end.x-w.start.x,w.end.y-w.start.y)/scale
        along=box.x2-box.x1 if abs(w.end.x-w.start.x)>abs(w.end.y-w.start.y) else box.y2-box.y1
        width=min(max(.45,along/scale),length*.65)
        if width<.15:continue
        offset=max(0,min(length-width,t*length-width/2))
        if any(o.wall_id==w.id and offset<o.offset_m+o.width_m and o.offset_m<offset+width for o in openings):
            continue
        openings.append(Opening(id='model-opening-'+str(i),source_detection_id='model-box-'+str(i),kind=box.category,wall_id=w.id,
            offset_m=round(offset,3),width_m=round(width,3),
            height_m=2.1 if box.category=='door' else 1.2,
            sill_m=0 if box.category=='door' else .9,inferred=True))
    return Geometry(width_px=base.width_px,height_px=base.height_px,
        px_per_meter=base.px_per_meter,scale_source=base.scale_source,
        rooms=[],walls=walls,openings=openings,
        warnings=['Model-generated draft: wall centerlines approximate YOLO bounding boxes.',
                  'The model did not reconstruct closed room polygons or floor surfaces.',
                  'Opening positions and physical dimensions are provisional; confirmation required.'])

def detection_audit(result:DetectorResult)->dict:
    """Explain why detection boxes do not become walls; never imply missing
    detections are absent from the architectural drawing."""
    counts={'wall_boxes':0,'accepted_wall_boxes':0,'below_confidence':0,
            'too_short':0,'not_elongated':0,'duplicate':0,
            'door_boxes':0,'window_boxes':0}
    kept,dropped=_model_wall_candidates(result)
    counts.update(dropped)
    counts['wall_boxes']=sum(b.category=='wall' for b in result.boxes)
    counts['door_boxes']=sum(b.category=='door' for b in result.boxes)
    counts['window_boxes']=sum(b.category=='window' for b in result.boxes)
    counts['accepted_wall_boxes']=len(kept)
    return {
       **counts,
       'diagnostic':'Counts explain losses AFTER YOLO detection. Walls never detected by YOLO require labeled ground truth to measure recall.',
       'pipeline':'YOLO bounding box → elongation/length filter → centerline → junction proposal → 3D'
    }
