import {nodeMap,wallEnds} from "./derive";
import type {PlanModel,Wall} from "./model";
import type {WallSide} from "./scene";
import {otherSide} from "./wallMaterials";

export type WallFace = {id:string;side:WallSide};

// Follow straight graph edges on the selected side until a corner or a
// partition on that side interrupts the wall face.
export function connectedWallFace(plan:PlanModel,face:WallFace):WallFace[]{
  const first=plan.walls.find(wall=>wall.id===face.id);
  if(!first)return [];
  const nodes=nodeMap(plan);
  const byNode=new Map<string,Wall[]>();
  const direction=(wall:Wall,node:string)=>{
    const [a,b]=wallEnds(plan,wall,nodes);
    const sign=node===wall.a?1:-1;
    const length=Math.hypot(b.x-a.x,b.y-a.y)||1;
    return {x:sign*(b.x-a.x)/length,y:sign*(b.y-a.y)/length};
  };
  for(const wall of plan.walls)for(const node of [wall.a,wall.b]){
    const edges=byNode.get(node);
    if(edges)edges.push(wall);
    else byNode.set(node,[wall]);
  }
  const forward=direction(first,first.a);
  const positive=face.side===(first.a<first.b?"a":"b")?1:-1;
  const normal={x:-forward.y*positive,y:forward.x*positive};
  const visited=new Set([first.id]);
  const faces=[face];
  for(const junction of [first.a,first.b]){
    let node=junction;
    let current=first;
    while(true){
      const incoming=direction(current,node);
      const edges=(byNode.get(node)??[]).filter(wall=>wall!==current).map(wall=>({wall,direction:direction(wall,node)}));
      if(edges.some(({direction:d})=>d.x*normal.x+d.y*normal.y>.12))break;
      const through=edges.filter(({direction:d})=>d.x*incoming.x+d.y*incoming.y<-.999);
      if(through.length!==1||visited.has(through[0].wall.id))break;
      const next=through[0].wall;
      const d=direction(next,next.a);
      const side=next.a<next.b?"a":"b";
      faces.push({id:next.id,side:-d.y*normal.x+d.x*normal.y>0?side:otherSide(side)});
      visited.add(next.id);
      node=next.a===node?next.b:next.a;
      current=next;
    }
  }
  return faces;
}
