"""Deterministic proposal: snap nearby joins and polygonize closed wall contours.

Shapely is a geometric solver, not an AI detector. This module never asserts
that detected lines are real structural walls. Results remain unverified and
the original detector boxes are retained separately by the calling route.
"""
from __future__ import annotations
from math import hypot
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points, unary_union, polygonize
from .geometry import Geometry, Room, Pt, Wall

def _dist(a, b):
    return hypot(a.x-b.x, a.y-b.y)

def propose_connected_geometry(g: Geometry, tolerance_px: float = 8.0,
                               min_area_ratio: float = 0.002) -> Geometry:
    if not 0 < tolerance_px <= 30: raise ValueError('tolerance_px must be in (0,30]')
    if not 0 < min_area_ratio < 1: raise ValueError('min_area_ratio must be in (0,1)')
    result=g.model_copy(deep=True)
    original=result.walls
    if not original:
        result.rooms=[]
        result.warnings=list(dict.fromkeys(result.warnings+['No walls to connect']))
        return result
    linework=[LineString([(w.start.x,w.start.y),(w.end.x,w.end.y)]) for w in original]
    updated=[]
    count=0
    for i,wall in enumerate(original):
        points=[]
        for endpoint in (wall.start,wall.end):
            candidate=Point(endpoint.x,endpoint.y)
            closest=(float('inf'),endpoint.x,endpoint.y)
            # Prefer exact endpoint-to-endpoint clusters, then T-junction on
            # an existing wall segment; do not snap along unrelated distant lines.
            for j,other in enumerate(original):
                if i==j: continue
                for q in (other.start,other.end):
                    d=_dist(endpoint,q)
                    if d<closest[0]: closest=(d,q.x,q.y)
            if closest[0]<=tolerance_px:
                x,y=closest[1:]
            else:
                best=(float('inf'),endpoint.x,endpoint.y)
                for j,line in enumerate(linework):
                    if i==j: continue
                    _,q=nearest_points(candidate,line)
                    d=candidate.distance(q)
                    if d<best[0]:best=(d,q.x,q.y)
                x,y=(best[1],best[2]) if best[0]<=tolerance_px else (endpoint.x,endpoint.y)
            if hypot(endpoint.x-x,endpoint.y-y)>.01:count+=1
            points.append(Pt(x=round(x,3),y=round(y,3)))
        if _dist(*points)<2:
            updated.append(wall)
            continue
        updated.append(wall.model_copy(update={'start':points[0],'end':points[1]}))
    result.walls=updated
    segments=[LineString([(w.start.x,w.start.y),(w.end.x,w.end.y)]) for w in updated]
    planar=unary_union(segments)
    min_area=g.width_px*g.height_px*min_area_ratio
    regions=[]
    for poly in polygonize(planar):
        if poly.is_empty or not poly.is_valid or poly.area<min_area:continue
        coords=list(poly.exterior.coords)[:-1]
        if len(coords)<3:continue
        # no holes invented; complex hole polygons must be reviewed separately.
        if len(poly.interiors):continue
        if any(not (-.5<=x<=g.width_px+.5 and -.5<=y<=g.height_px+.5) for x,y in coords):continue
        regions.append(poly)
    regions.sort(key=lambda p:(round(p.bounds[1],2),round(p.bounds[0],2),-p.area))
    result.rooms=[Room(id='auto-room-'+str(i+1),label='Proposed room '+str(i+1),
                       confidence=0.0,points=[Pt(x=round(x,3),y=round(y,3))
                       for x,y in list(poly.exterior.coords)[:-1]])
                  for i,poly in enumerate(regions)]
    result.structure_reviewed=False
    result.warnings=list(dict.fromkeys([
        w for w in result.warnings if 'No room polygons' not in w and
        'did not reconstruct closed room polygons' not in w
    ]+[
        f'Topology proposal: {count} endpoints adjusted within {tolerance_px:g}px',
        f'{len(regions)} enclosed regions found; these are unverified room hypotheses',
        'Open contours cannot become floors; inspect false-positive walls and junctions'
    ]))
    return result
