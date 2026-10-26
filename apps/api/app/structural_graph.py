"""Read-only canonical junction graph derived from wall centerlines.

Preserves source wall IDs, exposes shared node IDs and split edges at T/X
junctions. Never connects nearby parallel walls or fills unsupported gaps.
Graph is a proposal, not a verified floor plan.
"""
from __future__ import annotations
from math import hypot
from pydantic import BaseModel, Field
from .geometry import Geometry, Pt

class Junction(BaseModel):
    id: str
    position: Pt
    connected_wall_ids: list[str]
    degree: int

class GraphEdge(BaseModel):
    id: str
    source_wall_id: str
    start_node_id: str
    end_node_id: str
    length_px: float

class StructuralGraph(BaseModel):
    nodes: list[Junction]
    edges: list[GraphEdge]
    disconnected_components: int
    dangling_nodes: int
    intersections: int
    warnings: list[str] = Field(default_factory=list)

def _distance(a:Pt,b:Pt)->float:
    return hypot(a.x-b.x,a.y-b.y)

def _project(p:Pt,a:Pt,b:Pt):
    dx=b.x-a.x;dy=b.y-a.y
    denom=dx*dx+dy*dy
    if denom<1e-9:return (0.,a,_distance(p,a))
    t=max(0.,min(1.,((p.x-a.x)*dx+(p.y-a.y)*dy)/denom))
    q=Pt(x=a.x+t*dx,y=a.y+t*dy)
    return t,q,_distance(p,q)

def _crossing(a:Pt,b:Pt,c:Pt,d:Pt):
    ux=b.x-a.x;uy=b.y-a.y
    vx=d.x-c.x;vy=d.y-c.y
    det=ux*vy-uy*vx
    if abs(det)<1e-8:return None
    dx=c.x-a.x;dy=c.y-a.y
    t=(dx*vy-dy*vx)/det
    u=(dx*uy-dy*ux)/det
    if 0<=t<=1 and 0<=u<=1:
        return t,u,Pt(x=a.x+t*ux,y=a.y+t*uy)
    return None

def build_structural_graph(geometry:Geometry,tolerance_px:float=5.)->StructuralGraph:
    if not 0<tolerance_px<=15:raise ValueError('tolerance must be in (0,15]')
    walls=geometry.walls
    # A node joins only coincident endpoints or a proven point on another
    # wall axis. Merely nearby PARALLEL lines are never connected.
    splits={w.id:[(0.,w.start),(1.,w.end)] for w in walls}
    intersection_count=0
    for i,a in enumerate(walls):
        for b in walls[i+1:]:
            cross=_crossing(a.start,a.end,b.start,b.end)
            if cross:
                ta,tb,p=cross
                splits[a.id].append((ta,p))
                splits[b.id].append((tb,p))
                intersection_count+=1
            # T joins: snap a loose endpoint to the interior axis only when
            # nearly on it, not near a different parallel wall.
            for source,target in ((a,b),(b,a)):
                for pt in (source.start,source.end):
                    t,q,dist=_project(pt,target.start,target.end)
                    if 1e-4<t<1-1e-4 and dist<=tolerance_px:
                        # Do not shift source walls here: only record a shared
                        # junction when coordinates already coincide closely.
                        if dist<=1.0:
                            splits[target.id].append((t,q))
    nodes=[]
    def node_for(p:Pt)->str:
        for node in nodes:
            if _distance(p,node.position)<=1.0:
                return node.id
        node_id=f'junction-{len(nodes)+1}'
        nodes.append(Junction(id=node_id,position=Pt(x=round(p.x,3),y=round(p.y,3)),
                              connected_wall_ids=[],degree=0))
        return node_id
    edges=[]
    for wall in walls:
        points=sorted(splits[wall.id],key=lambda x:x[0])
        dedup=[]
        for t,p in points:
            if not dedup or _distance(p,dedup[-1][1])>1.0:dedup.append((t,p))
        for idx,((_,a),(_,b)) in enumerate(zip(dedup,dedup[1:])):
            length=_distance(a,b)
            if length<=1:continue
            x=node_for(a);y=node_for(b)
            if x==y:continue
            edges.append(GraphEdge(id=f'{wall.id}:edge:{idx}',source_wall_id=wall.id,
                 start_node_id=x,end_node_id=y,length_px=round(length,3)))
    lookup={node.id:node for node in nodes}
    adjacency={node.id:set() for node in nodes}
    for edge in edges:
        u,v=edge.start_node_id,edge.end_node_id
        adjacency[u].add(v);adjacency[v].add(u)
        for id in (u,v):
            n=lookup[id]
            if edge.source_wall_id not in n.connected_wall_ids:
                n.connected_wall_ids.append(edge.source_wall_id)
            n.degree+=1
    visited=set();components=0
    for start in adjacency:
        if start in visited:continue
        components+=1
        stack=[start];visited.add(start)
        while stack:
            for nxt in adjacency[stack.pop()]:
                if nxt not in visited:visited.add(nxt);stack.append(nxt)
    dangling=sum(node.degree==1 for node in nodes)
    warnings=[]
    if dangling:warnings.append(f'{dangling} loose graph endpoints need review')
    if components>1:warnings.append(f'{components} disconnected structural groups')
    if geometry.openings:warnings.append('Opening anchors remain attached to original wall IDs, not split graph edges')
    return StructuralGraph(nodes=nodes,edges=edges,disconnected_components=components,
        dangling_nodes=dangling,intersections=intersection_count,warnings=warnings)
