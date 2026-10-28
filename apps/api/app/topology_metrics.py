"""Topology-level benchmark against independently reviewed CanonicalPlan ground truth.

Never treat model review labels or inferred room cycles as gold automatically.
All comparisons are bound to an identical source-image SHA256 and pixel frame.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from math import hypot
from pydantic import BaseModel, Field
from shapely.geometry import Polygon
from .plan_graph import CanonicalPlan
from .graph_validation import require_valid


class TopologyCase(BaseModel):
    source_preview_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    provider: str = Field(min_length=1)
    gold_standard: bool = False
    plan: CanonicalPlan


def _matching_map(pred, truth, matches):
    """Maximum cardinality assignment; no reuse of one ground-truth node."""
    choices = []
    for p in pred:
        choices.append([j for j,t in enumerate(truth) if matches(p,t)])
    chosen = {}
    def augment(i,seen):
        for j in choices[i]:
            if j in seen:continue
            seen.add(j)
            if j not in chosen or augment(chosen[j],seen):
                chosen[j]=i
                return True
        return False
    for i in range(len(pred)):
        augment(i,set())
    return {i:j for j,i in chosen.items()}


def _scores(matched, predicted, truth):
    precision = matched/predicted if predicted else (1. if truth==0 else 0.)
    recall = matched/truth if truth else (1. if predicted==0 else 0.)
    f1 = 2*precision*recall/(precision+recall) if precision+recall else 0.
    return {'matched':matched,'predicted':predicted,'ground_truth':truth,
            'precision':round(precision,4),'recall':round(recall,4),'f1':round(f1,4)}


def structural_health(plan: CanonicalPlan) -> dict:
    nodes = {n.id:n for n in plan.nodes}
    degrees = Counter()
    adjacency = {n.id:set() for n in plan.nodes}
    for wall in plan.walls:
        if wall.start_node_id not in nodes or wall.end_node_id not in nodes:
            continue
        degrees[wall.start_node_id]+=1
        degrees[wall.end_node_id]+=1
        adjacency[wall.start_node_id].add(wall.end_node_id)
        adjacency[wall.end_node_id].add(wall.start_node_id)
    visited=set()
    components=0
    for node_id in adjacency:
        if node_id in visited or not adjacency[node_id]:
            continue
        components+=1
        stack=[node_id];visited.add(node_id)
        while stack:
            for neighbor in adjacency[stack.pop()]:
                if neighbor not in visited:
                    visited.add(neighbor);stack.append(neighbor)
    return {
        'wall_edges':len(plan.walls),
        'shared_junctions':len(plan.nodes),
        'connected_components':components,
        'dangling_nodes':sum(degrees[n.id]==1 for n in plan.nodes),
        'supported_room_cycles':len(plan.rooms),
        'confirmed_rooms':sum(r.verified for r in plan.rooms),
        'hosted_openings':len(plan.openings),
        'unresolved_opening_anchors':len(plan.pending_openings),
        'scale_confirmed':plan.px_per_meter is not None and plan.scale_source=='user_confirmed',
    }


def _face_polygon(plan: CanonicalPlan, room):
    nodes={n.id:n.point for n in plan.nodes}
    walls={w.id:w for w in plan.walls}
    vertices=[]
    for edge in room.boundary:
        wall=walls[edge.wall_id]
        p=nodes[wall.start_node_id if edge.forward else wall.end_node_id]
        vertices.append((p.x,p.y))
    return Polygon(vertices)


def compare_topology(truth:TopologyCase, prediction:TopologyCase, tolerance_px:float=5.) -> dict:
    if not truth.gold_standard:
        raise ValueError('Reference is not independently confirmed ground truth')
    if prediction.gold_standard:
        raise ValueError('Prediction should not be marked as ground truth')
    if tolerance_px<=0 or tolerance_px>30:
        raise ValueError('Tolerance must be in (0,30] pixels')
    if truth.source_preview_sha256!=prediction.source_preview_sha256:
        raise ValueError('Image SHA256 mismatch; cannot compare distinct plans or crops')
    a,b=truth.plan,prediction.plan
    if (a.width_px,a.height_px)!=(b.width_px,b.height_px):
        raise ValueError('Pixel coordinate frame mismatch')
    require_valid(a);require_valid(b)
    pred_nodes=b.nodes;truth_nodes=a.nodes
    correspondence=_matching_map(pred_nodes,truth_nodes,lambda x,y:
         hypot(x.point.x-y.point.x,x.point.y-y.point.y)<=tolerance_px)
    node_scores=_scores(len(correspondence),len(pred_nodes),len(truth_nodes))
    truth_index={n.id:i for i,n in enumerate(truth_nodes)}
    pred_index={n.id:i for i,n in enumerate(pred_nodes)}
    truth_edge_keys=Counter(frozenset((
         truth_index[w.start_node_id],truth_index[w.end_node_id])) for w in a.walls)
    used=Counter()
    matched_wall_keys={}
    for wall in b.walls:
        x=correspondence.get(pred_index[wall.start_node_id])
        y=correspondence.get(pred_index[wall.end_node_id])
        if x is None or y is None:continue
        key=frozenset((x,y))
        if used[key] < truth_edge_keys[key]:
            used[key]+=1
            matched_wall_keys[wall.id]=key
    wall_scores=_scores(len(matched_wall_keys),len(b.walls),len(a.walls))
    truth_polys=[_face_polygon(a,r) for r in a.rooms]
    pred_polys=[_face_polygon(b,r) for r in b.rooms]
    def overlapping(poly1,poly2):
        u=poly1.union(poly2).area
        return u>0 and poly1.intersection(poly2).area/u>=.5
    rooms_matched=_matching_map(pred_polys,truth_polys,overlapping)
    room_scores=_scores(len(rooms_matched),len(pred_polys),len(truth_polys))
    # Opening identity is tied to source detection if present, otherwise ID.
    truth_openings={o.source_detection_id or o.id:o for o in a.openings}
    truth_walls={w.id:w for w in a.walls}
    matched_openings=0
    matched_hosts=0
    for op in b.openings:
        ref=truth_openings.get(op.source_detection_id or op.id)
        if ref is None:continue
        matched_openings+=1
        source_wall=truth_walls[ref.wall_id]
        key=frozenset((truth_index[source_wall.start_node_id],truth_index[source_wall.end_node_id]))
        if matched_wall_keys.get(op.wall_id)==key:
            matched_hosts+=1
    return {
        'source_sha256':truth.source_preview_sha256,
        'prediction_provider':prediction.provider,
        'junctions':node_scores,
        'wall_adjacency_edges':wall_scores,
        'room_regions_at_iou_0_5':room_scores,
        'opening_host_accuracy':round(matched_hosts/len(a.openings),4) if a.openings else None,
        'opening_identity_recall':round(matched_openings/len(a.openings),4) if a.openings else None,
        'reference_health':structural_health(a),
        'prediction_health':structural_health(b),
        'limitations':[
          'Wall adjacency scores topological edges, not raster coverage or wall-face thickness.',
          'Junction matching uses a bounded pixel tolerance; dimensions must be benchmarked separately.',
          'Room matches use per-room IoU >= 0.5, not semantic room labels.',
          'User correction time needs measured review sessions and cannot be inferred here.',
        ],
    }


def main():
    parser=argparse.ArgumentParser(description='Evaluate canonical floor-plan topology against confirmed gold')
    parser.add_argument('--truth',type=Path,required=True)
    parser.add_argument('--prediction',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--tolerance-px',type=float,default=5.)
    args=parser.parse_args()
    gold=TopologyCase.model_validate_json(args.truth.read_text())
    candidate=TopologyCase.model_validate_json(args.prediction.read_text())
    report=compare_topology(gold,candidate,args.tolerance_px)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()
