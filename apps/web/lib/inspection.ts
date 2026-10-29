export type InspectionIssue={kind:string;object:number;objects?:number[];message?:string;x?:number;y?:number};
type Mask={polygon:[number,number][]};
export type Region=InspectionIssue & {objects:number[];x?:number;y?:number};
// Existing saved revisions may contain unclustered issues. Group them for display
// without mutating their source data; use fixed anchors to avoid chaining clusters.
export function inspectionRegions(issues:InspectionIssue[],objects:Mask[],radius=8):Region[]{
 const groups:Region[]=[];
 const cells=new Map<string,Region[]>();
 for(const item of issues){
  const poly=objects[item.object]?.polygon;
  const x=item.x??(poly?.length?poly.reduce((n,p)=>n+p[0],0)/poly.length:undefined);
  const y=item.y??(poly?.length?poly.reduce((n,p)=>n+p[1],0)/poly.length:undefined);
  let match:Region|undefined;
  if(x!==undefined&&y!==undefined){const gx=Math.floor(x/radius),gy=Math.floor(y/radius);
   for(let a=gx-1;a<=gx+1&&!match;a++)for(let b=gy-1;b<=gy+1&&!match;b++)match=cells.get(`${item.kind}:${a}:${b}`)?.find(r=>Math.hypot(r.x!-x,r.y!-y)<=radius);
  }
  const ids=item.objects?.length?item.objects:[item.object];
  if(match){for(const id of ids)if(!match.objects.includes(id))match.objects.push(id);continue}
  const region={...item,objects:[...new Set(ids)],x,y};groups.push(region);
  if(x!==undefined&&y!==undefined){const key=`${item.kind}:${Math.floor(x/radius)}:${Math.floor(y/radius)}`;cells.set(key,[...(cells.get(key)||[]),region]);}
 }
 return groups;
}
export function issueLabel(kind:string):string {return ({short_wall:'Short walls',complex_wall_mask:'Complex walls',opening_host:'Opening hosts',opening_span_crosses_junction:'Openings at junctions'} as Record<string,string>)[kind]||kind.replaceAll('_',' ')}
