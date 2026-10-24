import type {Geometry,Pt,Wall,Opening} from './api';
export type DraftEdge={id:string;start:Pt;end:Pt;thickness_m:number;height_m:number};
const dist=(a:Pt,b:Pt)=>Math.hypot(a.x-b.x,a.y-b.y);
export function editableEdges(g:Geometry):DraftEdge[]{
  const result:DraftEdge[]=[];
  const seen=new Set<string>();
  for(const room of g.rooms)room.points.forEach((a,i)=>{
    const b=room.points[(i+1)%room.points.length];
    if(dist(a,b)<2)return;
    const key=[a,b].map(v=>v.x.toFixed(2)+','+v.y.toFixed(2)).sort().join('|');
    if(seen.has(key))return;seen.add(key);
    result.push({id:'boundary:'+room.id+':'+i,start:a,end:b,thickness_m:.15,height_m:2.8});
  });
  for(const w of g.walls){
    // Starter wall w0-w3 is a legacy duplicate of the placeholder room outline.
    if(/^w[0-3]$/.test(w.id) && g.rooms.length===1)continue;
    const middle={x:(w.start.x+w.end.x)/2,y:(w.start.y+w.end.y)/2};
    if(result.some(e=>segmentDistance(middle,e)<3 && Math.abs(dist(e.start,e.end)-dist(w.start,w.end))<6))continue;
    result.push(w);
  }
  return result;
}
export function segmentDistance(p:Pt,e:{start:Pt;end:Pt}):number{
  const {start:a,end:b}=e,dx=b.x-a.x,dy=b.y-a.y,den=dx*dx+dy*dy;
  const t=den?Math.max(0,Math.min(1,((p.x-a.x)*dx+(p.y-a.y)*dy)/den)):0;
  return Math.hypot(p.x-a.x-t*dx,p.y-a.y-t*dy);
}
export function snapPoint(p:Pt,g:Geometry,anchor?:Pt,threshold=12):Pt{
  let point={x:p.x,y:p.y};
  const vertices:Pt[]=[...g.rooms.flatMap(r=>r.points),...g.walls.flatMap(w=>[w.start,w.end])];
  const nearest=vertices.reduce<{p:Pt;d:number}|null>((best,v)=>{
    const d=dist(v,p);return d<threshold&&(!best||d<best.d)?{p:v,d}:best;
  },null);
  if(nearest)return {...nearest.p};
  if(anchor){
    if(Math.abs(p.x-anchor.x)<threshold)point.x=anchor.x;
    if(Math.abs(p.y-anchor.y)<threshold)point.y=anchor.y;
    // Constrain nearly-orthogonal lines; don't force genuine diagonal plans.
    const dx=p.x-anchor.x,dy=p.y-anchor.y;
    if(Math.abs(dy)<Math.abs(dx)*.12)point.y=anchor.y;
    else if(Math.abs(dx)<Math.abs(dy)*.12)point.x=anchor.x;
  }
  // Snap to existing infinite wall axes only within segment bounds.
  if(!anchor)for(const e of editableEdges(g)){
    const dx=e.end.x-e.start.x,dy=e.end.y-e.start.y;
    if(Math.abs(dx)<2 && Math.abs(point.x-e.start.x)<threshold &&
      point.y>=Math.min(e.start.y,e.end.y)-threshold&&point.y<=Math.max(e.start.y,e.end.y)+threshold)point.x=e.start.x;
    if(Math.abs(dy)<2 && Math.abs(point.y-e.start.y)<threshold &&
      point.x>=Math.min(e.start.x,e.end.x)-threshold&&point.x<=Math.max(e.start.x,e.end.x)+threshold)point.y=e.start.y;
  }
  return {x:Math.round(Math.max(0,Math.min(g.width_px,point.x))),y:Math.round(Math.max(0,Math.min(g.height_px,point.y)))};
}
export function openingPlacement(edge:DraftEdge,p:Pt,g:Geometry,kind:'door'|'window'):Opening|null{
  if(!g.px_per_meter)return null;
  const len=dist(edge.start,edge.end),dx=edge.end.x-edge.start.x,dy=edge.end.y-edge.start.y;
  const meters=len/g.px_per_meter, width=Math.min(kind==='door'?.9:1.2,meters*.65);
  if(width<=.1)return null;
  const t=Math.max(0,Math.min(1,((p.x-edge.start.x)*dx+(p.y-edge.start.y)*dy)/(len*len)));
  const offset=Math.max(0,Math.min(meters-width,t*meters-width/2));
  return {id:'opening-'+crypto.randomUUID(),kind,wall_id:edge.id,
    offset_m:Number(offset.toFixed(3)),width_m:Number(width.toFixed(3)),
    height_m:kind==='door'?2.1:1.2,sill_m:kind==='door'?0:.9,inferred:true};
}
