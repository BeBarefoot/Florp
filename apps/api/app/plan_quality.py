"""Explicit readiness diagnostics; graph health is not an accuracy certificate."""
from .geometry import Geometry
from .connectivity_preview import without_starter, is_untouched_starter_wall
from .graph_adapter import from_geometry
from .graph_validation import validate_plan
from .global_reconstruction import topology


def assess_plan(geometry: Geometry, labels: list[dict] | None = None) -> dict:
    clean=without_starter(geometry)
    graph=from_geometry(clean)
    health=topology(graph)
    nodes={n.id:n for n in graph.nodes}
    walls={w.id:w for w in graph.walls}
    incidence={w.id:0 for w in graph.walls}
    for room in graph.rooms:
        for edge in room.boundary:incidence[edge.wall_id]+=1
    source_edges={}
    for wall in graph.walls:source_edges.setdefault(wall.source_wall_id or wall.id,[]).append(wall.id)
    shared={source for source,edges in source_edges.items() if all(incidence[e]==2 for e in edges)}
    room_faces=[]
    for room in graph.rooms:
        boundary=[walls[e.wall_id] for e in room.boundary]
        sources=list(dict.fromkeys(w.source_wall_id or w.id for w in boundary))
        room_faces.append({'id':room.id,'points':[nodes[w.start_node_id if e.forward else w.end_node_id].point.model_dump()
                         for e,w in zip(room.boundary,boundary)],'source_wall_ids':sources,
                         'shared_source_wall_ids':[s for s in sources if s in shared],'verified':False})
    incident={n.id:[] for n in graph.nodes}
    for w in graph.walls:
        for node in (w.start_node_id,w.end_node_id):incident[node].append(w.source_wall_id or w.id)
    loose=[{'id':n.id,'point':n.point.model_dump(),'source_wall_ids':incident[n.id]}
           for n in graph.nodes if len(incident[n.id])==1]
    problems=[]
    if not clean.walls:problems.append('No structural walls have been saved')
    if health['components']>1:problems.append(f"{health['components']} disconnected wall groups need review")
    if health['dangling']:problems.append(f"{health['dangling']} loose endpoints need review")
    if not graph.rooms:problems.append('No closed wall-supported room faces')
    problems.extend(validate_plan(graph))
    if graph.pending_openings:problems.append(f'{len(graph.pending_openings)} unresolved opening anchors')
    classified={r['candidate_id'] for r in labels or [] if r.get('decision') in ('door','window')}
    represented={o.source_detection_id for o in clean.openings if o.source_detection_id}
    unresolved=sorted(classified-represented)
    if unresolved:problems.append(f'{len(unresolved)} classified openings have no physical host/span')
    metric=[]
    if clean.scale_source!='user_confirmed' or not clean.px_per_meter:metric.append('Confirm metric scale')
    if any(o.inferred for o in clean.openings):metric.append('Confirm opening dimensions')
    if not clean.structure_reviewed:metric.append('Independently review all structural geometry')
    return {'geometry':clean.model_dump(),'topology':health,'room_faces':room_faces,'loose_endpoints':loose,
            'placeholder_wall_ids':[w.id for w in geometry.walls if is_untouched_starter_wall(geometry,w)],
            'unresolved_opening_ids':unresolved,'structural_issues':list(dict.fromkeys(problems)),
            'metric_issues':metric,'ready_for_metric_scene':not problems and not metric,
            'training_ground_truth':False,
            'note':'These checks identify structural defects; passing them does not prove extraction accuracy.'}
