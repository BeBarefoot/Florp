"""Coalesce inspection warnings without changing annotations or geometry."""
from math import hypot
from shapely.geometry import Polygon

# Thresholds are in source pixels, applied only to warning generation.
MIN_WARNING_AREA = 4.0
MIN_COMPLEX_AREA = 16.0
CLUSTER_RADIUS = 8.0

def regional_issues(issues, objects):
    regions=[]; suppressed=0
    for issue in issues:
        index=issue['object']
        if index<0 or index>=len(objects):
            regions.append(dict(issue,objects=[index]));continue
        polygon=Polygon(objects[index]['polygon']);bounds=polygon.bounds
        length=max(bounds[2]-bounds[0],bounds[3]-bounds[1])
        if issue['kind'] in ('short_wall','complex_wall_mask') and (polygon.area<MIN_WARNING_AREA or (issue['kind']=='complex_wall_mask' and (polygon.area<MIN_COMPLEX_AREA or length<4))):
            suppressed+=1;continue
        p=polygon.representative_point();x,y=p.x,p.y
        # Distance from the fixed representative avoids transitive merging of an entire building.
        cluster=next((r for r in regions if r['kind']==issue['kind'] and 'x' in r and hypot(r['x']-x,r['y']-y)<=CLUSTER_RADIUS),None)
        ids=issue.get('objects',[index])
        if cluster:
            cluster['objects'].extend(i for i in ids if i not in cluster['objects'])
        else:
            regions.append(dict(issue,objects=list(dict.fromkeys(ids)),x=x,y=y))
    return regions, suppressed
