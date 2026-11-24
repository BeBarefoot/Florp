import { openingEnds } from "./derive";
import { wallPieces } from "./mesh";
import type { PlanModel, Pt } from "./model";
import { contains, footprint, type Scene } from "./scene";

export const roomsOf = (m: PlanModel) => [...m.rooms, ...(m.roomZones || [])].slice(0, 990);

export function walkSpace(m: PlanModel, scale: number, scene: Scene, eye = 1.6,
  pieces = wallPieces(m), nodeMap = new Map(m.nodes.map(n=>[n.id,n]))) {
  const rooms = roomsOf(m);
  const {objects, closedDoorIds} = scene;
  function clearance(p:Pt, walking=false) {
    let nearest=Infinity;
    for(const wall of pieces) {
      const x=p.x*scale-wall.centre[0], z=p.y*scale-wall.centre[1], a=-wall.angle;
      const u=x*Math.cos(a)+z*Math.sin(a)+wall.lengthM/2;
      const v=-x*Math.sin(a)+z*Math.cos(a);
      for(const c of wall.chunks) {
        if(c.low>(walking?eye+.12:eye)||c.high<(walking ? .02 : eye))continue;
        nearest=Math.min(nearest,Math.hypot(Math.max(0,c.start-u,u-c.end),Math.max(0,Math.abs(v)-wall.thicknessM/2)));
      }
    }
    for(const o of m.openings) {
      if(o.kind!=="door"||o.status!=="confirmed"||!closedDoorIds?.includes(o.id)||
         (!walking && o.heightM<eye))continue;
      const ends=openingEnds(m,o,nodeMap);if(!ends)continue;
      const [a,b]=ends, dx=b.x-a.x, dy=b.y-a.y, len2=dx*dx+dy*dy;
      if(len2<1e-8)continue;
      const t=Math.min(1,Math.max(0,((p.x-a.x)*dx+(p.y-a.y)*dy)/len2));
      nearest=Math.min(nearest,Math.max(0,Math.hypot(p.x-a.x-t*dx,p.y-a.y-t*dy)*scale-.02));
    }
    return nearest;
  }
  // Room floor polygons can end at the inside wall face on each side of a door.
  // Include the threshold of an open, hosted door in the walkable footprint.
  function inDoorway(p:Pt){
    return m.openings.some(o=>{
      if(o.kind!=="door" || o.status!=="confirmed" || closedDoorIds?.includes(o.id))return false;
      const wall=m.walls.find(w=>w.id===o.hostWallId);
      const ends=openingEnds(m,o,nodeMap);
      if(!wall || !ends || o.sillM>.02 || o.heightM<eye+.12)return false;
      const [a,b]=ends, dx=b.x-a.x, dy=b.y-a.y;
      const length=Math.hypot(dx,dy);
      if(length<=0)return false;
      const along=((p.x-a.x)*dx+(p.y-a.y)*dy)/length;
      const across=Math.abs((p.x-a.x)*dy-(p.y-a.y)*dx)/length;
      return along*scale>=.3 && (length-along)*scale>=.3 && across<=wall.thicknessPx/2+.5;
    });
  }
  function validCamera(p:Pt, walking=false){
    return (rooms.some(r=>contains(p,r.polygon)) || inDoorway(p)) && clearance(p,walking)>=.3 &&
      !objects.some(o=>contains(p,footprint(o,scale)));
  }
  return { clearance, validCamera };
}

export function findRoomView(polygon: Pt[], scale: number, valid: (p: Pt, walking: boolean) => boolean, near?: Pt) {
  const winding = Math.sign(polygon.reduce((sum,p,index)=>{
    const next=polygon[(index+1)%polygon.length];
    return sum+p.x*next.y-p.y*next.x;
  },0));
  const corners = polygon.map((point,index)=>({point,index}));
  if (near) corners.sort((a,b)=>Math.hypot(a.point.x-near.x,a.point.y-near.y)-Math.hypot(b.point.x-near.x,b.point.y-near.y));
  for (const {point,index} of corners) {
    const before=polygon[(index+polygon.length-1)%polygon.length];
    const after=polygon[(index+1)%polygon.length];
    const turn=(point.x-before.x)*(after.y-point.y)-(point.y-before.y)*(after.x-point.x);
    if (turn*winding<=0) continue;
    const first=Math.hypot(before.x-point.x,before.y-point.y);
    const second=Math.hypot(after.x-point.x,after.y-point.y);
    if (!first || !second) continue;
    const x=(before.x-point.x)/first+(after.x-point.x)/second;
    const y=(before.y-point.y)/first+(after.y-point.y)/second;
    const length=Math.hypot(x,y);
    if (length<1e-6) continue;
    for (const metres of [.46,.65,.9,1.2]) {
      const position={x:point.x+x/length*metres/scale,y:point.y+y/length*metres/scale};
      if (contains(position,polygon)&&valid(position,true))
        return {position,yaw:Math.atan2(y,x)*180/Math.PI};
    }
  }
}

export function findWalkStart(plan: PlanModel, scale: number, valid: (p: Pt, walking: boolean) => boolean) {
  for (const {polygon} of roomsOf(plan)) {
    if (!polygon.length) continue;
    const corner=findRoomView(polygon,scale,valid);
    if (corner) return corner;
    const xs = polygon.map(p=>p.x), ys = polygon.map(p=>p.y);
    const left = Math.min(...xs), top = Math.min(...ys);
    const width = Math.max(...xs) - left, height = Math.max(...ys) - top;
    const center = {x:left + width/2,y:top + height/2};
    if (contains(center,polygon)&&valid(center,true)) return {position:center,yaw:0};
    for (let row = 1; row < 8; row++) {
      for (let column = 1; column < 8; column++) {
        const position = {x:left + width*column/8,y:top + height*row/8};
        if (contains(position,polygon)&&valid(position,true)) return {position,yaw:0};
      }
    }
  }
}
