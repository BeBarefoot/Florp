"""Convert long wall detection boxes into conservative, unverified wall centerlines."""
from math import hypot
from .geometry import Geometry,Wall,Pt,Opening
from .pretrained_detector import DetectorResult

def _projection(x,y,w):
    dx=w.end.x-w.start.x;dy=w.end.y-w.start.y
    length=dx*dx+dy*dy
    t=max(0,min(1,((x-w.start.x)*dx+(y-w.start.y)*dy)/length)) if length else 0
    return hypot(x-w.start.x-dx*t,y-w.start.y-dy*t),t

def reconstruct(result:DetectorResult, base:Geometry)->Geometry:
    if (result.image_width,result.image_height)!=(base.width_px,base.height_px):
        raise ValueError('Image dimensions mismatch')
    walls=[]
    for i,box in enumerate(result.boxes):
        if box.category!='wall' or box.confidence<.35:continue
        bw=box.x2-box.x1;bh=box.y2-box.y1
        if max(bw,bh)<max(22,min(base.width_px,base.height_px)*.075):continue
        if max(bw,bh)/max(1,min(bw,bh))<2.3:continue
        if bw>=bh:
            y=(box.y1+box.y2)/2
            a=Pt(x=box.x1,y=y);b=Pt(x=box.x2,y=y)
        else:
            x=(box.x1+box.x2)/2
            a=Pt(x=x,y=box.y1);b=Pt(x=x,y=box.y2)
        if any(hypot(a.x-w.start.x,a.y-w.start.y)<7 and hypot(b.x-w.end.x,b.y-w.end.y)<7 for w in walls):
            continue
        walls.append(Wall(id='model-'+str(i),start=a,end=b,inferred=True))
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
    kept=[]
    for i,b in enumerate(result.boxes):
        if b.category in ('door','window'):
            counts[b.category+'_boxes']+=1
        if b.category!='wall':continue
        counts['wall_boxes']+=1
        if b.confidence<.35:
            counts['below_confidence']+=1;continue
        bw=b.x2-b.x1;bh=b.y2-b.y1
        if max(bw,bh)<max(22,min(result.image_width,result.image_height)*.075):
            counts['too_short']+=1;continue
        if max(bw,bh)/max(1,min(bw,bh))<2.3:
            counts['not_elongated']+=1;continue
        if bw>=bh:
            a=(b.x1,(b.y1+b.y2)/2);z=(b.x2,(b.y1+b.y2)/2)
        else:
            a=((b.x1+b.x2)/2,b.y1);z=((b.x1+b.x2)/2,b.y2)
        if any(hypot(a[0]-old[0][0],a[1]-old[0][1])<7 and
               hypot(z[0]-old[1][0],z[1]-old[1][1])<7 for old in kept):
            counts['duplicate']+=1;continue
        kept.append((a,z))
    counts['accepted_wall_boxes']=len(kept)
    return {
       **counts,
       'diagnostic':'Counts explain losses AFTER YOLO detection. Walls never detected by YOLO require labeled ground truth to measure recall.',
       'pipeline':'YOLO bounding box → elongation/length filter → centerline → junction proposal → 3D'
    }
