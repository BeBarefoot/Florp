"""Non-mutating topology audit over the current wall draft."""
from math import hypot
from pydantic import BaseModel, Field
from .geometry import Geometry

class TopologyAudit(BaseModel):
    wall_count: int
    junction_count: int
    disconnected_components: int
    dangling_endpoints: int
    crossing_pairs: list[tuple[str,str]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

def audit_topology(g: Geometry, tolerance: float = 6) -> TopologyAudit:
    if tolerance <= 0: raise ValueError("tolerance must be positive")
    walls = g.walls
    points = []
    neighbors = []
    for wall in walls:
        for p in [wall.start, wall.end]:
            index = next((i for i,q in enumerate(points) if hypot(p.x-q.x,p.y-q.y)<=tolerance),None)
            if index is None:
                index=len(points)
                points.append(p)
                neighbors.append(set())
            neighbors[index].add(wall.id)
    parent = {w.id:w.id for w in walls}
    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k=parent[k]
        return k
    for adj in neighbors:
        items=list(adj)
        for other in items[1:]:
            parent[find(other)] = find(items[0])
    crossings=[]
    def intersection(a,b):
        ux=a.end.x-a.start.x;uy=a.end.y-a.start.y
        vx=b.end.x-b.start.x;vy=b.end.y-b.start.y
        det=ux*vy-uy*vx
        if abs(det)<1e-9:return False
        dx=b.start.x-a.start.x;dy=b.start.y-a.start.y
        t=(dx*vy-dy*vx)/det
        u=(dx*uy-dy*ux)/det
        return 0.001<t<0.999 and 0.001<u<0.999
    for i,a in enumerate(walls):
        for b in walls[i+1:]:
            if intersection(a,b):crossings.append((a.id,b.id))
    components=len({find(w.id) for w in walls})
    dangling=sum(len(adj)==1 for adj in neighbors)
    notes=[]
    if dangling:notes.append("Dangling endpoints require junction review")
    if crossings:notes.append("Interior crossings require explicit junction review")
    if not g.rooms:notes.append("No room polygons: floor reconstruction not justified")
    if not g.px_per_meter:notes.append("Physical scale unconfirmed")
    return TopologyAudit(wall_count=len(walls),junction_count=sum(len(a)>1 for a in neighbors),
        disconnected_components=components,dangling_endpoints=dangling,crossing_pairs=crossings,notes=notes)
