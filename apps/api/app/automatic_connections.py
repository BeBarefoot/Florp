"""Conservative, image-supported endpoint corrections for unsaved drafts."""
from math import ceil,hypot
from PIL import Image
from .connectivity_preview import preview_connectivity
from .structural_graph import build_structural_graph


def repair(geometry, image:Image.Image, opening_boxes:list[tuple[float,float,float,float]]):
    if image.size!=(geometry.width_px,geometry.height_px):raise ValueError('Source image dimensions mismatch')
    before=build_structural_graph(geometry)
    result=geometry.model_copy(deep=True)
    # Never change already-confirmed structures or invalidate existing room polygons.
    if geometry.structure_reviewed or geometry.rooms:
        return result,[],before
    proposal=preview_connectivity(geometry,tolerance_px=4)
    gray=image.convert('L'); pixels=gray.load();w,h=image.size
    grouped={}
    for change in proposal.changes:
        key=(change.reason,round(change.proposed.x,2),round(change.proposed.y,2)) if change.reason=='perpendicular corner' else (change.wall_id,change.endpoint)
        grouped.setdefault(key,[]).append(change)
    original_walls={x.id:x for x in geometry.walls}
    def allowed(change):
        wall=original_walls[change.wall_id]
        if wall.id.startswith('user-') or any(o.wall_id==wall.id for o in geometry.openings):return False
        if any(hypot(n.position.x-change.original.x,n.position.y-change.original.y)<=1 and n.degree!=1 for n in before.nodes):return False
        for x1,y1,x2,y2 in opening_boxes:
            if any(min(x1,x2)-6<=p.x<=max(x1,x2)+6 and min(y1,y2)-6<=p.y<=max(y1,y2)+6 for p in (change.original,change.proposed)):
                return False
        # Demand source ink along the entire short adjustment, not just end caps.
        length=hypot(change.original.x-change.proposed.x,change.original.y-change.proposed.y)
        for i in range(1,max(2,ceil(length))):
            t=i/max(2,ceil(length));x=round(change.original.x+(change.proposed.x-change.original.x)*t);y=round(change.original.y+(change.proposed.y-change.original.y)*t)
            if not any(pixels[xx,yy]<150 for xx in range(max(0,x-1),min(w,x+2)) for yy in range(max(0,y-1),min(h,y+2))):return False
        return True
    accepted=[]
    for group in grouped.values():
        if group[0].reason=='perpendicular corner' and len(group)!=2:continue
        if not all(allowed(c) for c in group):continue
        candidate=result.model_copy(deep=True);by_id={wall.id:wall for wall in candidate.walls}
        for c in group:setattr(by_id[c.wall_id],c.endpoint,c.proposed.model_copy(deep=True))
        old=build_structural_graph(result);new=build_structural_graph(candidate)
        if new.disconnected_components>old.disconnected_components or new.dangling_nodes>old.dangling_nodes or new.intersections>old.intersections:continue
        if new.disconnected_components==old.disconnected_components and new.dangling_nodes==old.dangling_nodes:continue
        result=candidate;accepted.extend(group)
    if accepted:
        result.structure_reviewed=False
        result.warnings=list(dict.fromkeys(result.warnings+['Short image-supported junctions were automatically adjusted; review before verification.']))
    return result,accepted,build_structural_graph(result)
