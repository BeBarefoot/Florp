import {nodeMap,openingEnds} from "./derive";
import type {PlanModel,Pt} from "./model";
import {contains,footprint,intersects,type Item} from "./scene";
import {roomsOf} from "./walkSpace";

function crosses(a:Pt,b:Pt,c:Pt,d:Pt) {
  const side=(p:Pt,q:Pt,r:Pt)=>(q.x-p.x)*(r.y-p.y)-(q.y-p.y)*(r.x-p.x);
  return side(a,b,c)*side(a,b,d)<0 && side(c,d,a)*side(c,d,b)<0;
}

export function fitsFloor(plan:PlanModel,item:Item,scale:number) {
  const corners=footprint(item,scale);
  return roomsOf(plan).some(({polygon})=>
    corners.every(p=>contains(p,polygon)) && !corners.some((p,i)=>
      polygon.some((q,j)=>crosses(p,corners[(i+1)%corners.length],q,polygon[(j+1)%polygon.length]))));
}

function tightGaps(outline:Pt[], boundaries:{polygon:Pt[];interior:boolean}[],scale:number) {
  const gaps:Pt[][]=[];
  for(let i=0;i<outline.length;i++){
    const a=outline[i], b=outline[(i+1)%outline.length];
    const length=Math.hypot(b.x-a.x,b.y-a.y);
    const u={x:(b.x-a.x)/length,y:(b.y-a.y)/length};
    const n={x:u.y,y:-u.x};
    for(const {polygon,interior} of boundaries){
      const winding=polygon.reduce((sum,p,j)=>{
        const q=polygon[(j+1)%polygon.length];
        return sum+p.x*q.y-p.y*q.x;
      },0);
      for(let j=0;j<polygon.length;j++){
        const c=polygon[j],d=polygon[(j+1)%polygon.length];
        const facing=((d.x-c.x)*u.x+(d.y-c.y)*u.y)*Math.sign(winding);
        if(interior?facing<=0:facing>=0)continue;
        const cAcross=(c.x-a.x)*n.x+(c.y-a.y)*n.y;
        const dAcross=(d.x-a.x)*n.x+(d.y-a.y)*n.y;
        const distance=(cAcross+dAcross)/2;
        if(distance*scale<.15||distance*scale>=.6||
          Math.abs(cAcross-dAcross)>0.1*Math.hypot(d.x-c.x,d.y-c.y))continue;
        const [first,last]=[c,d].map(p=>(p.x-a.x)*u.x+(p.y-a.y)*u.y).sort((x,y)=>x-y);
        const lo=Math.max(0,first),hi=Math.min(length,last);
        if((hi-lo)*scale<.45)continue;
        gaps.push([[lo,0],[hi,0],[hi,distance],[lo,distance]].map(([x,y])=>({
          x:a.x+x*u.x+y*n.x,y:a.y+x*u.y+y*n.y,
        })));
      }
    }
  }
  return gaps;
}

export function furnitureFit(plan:PlanModel,item:Item,objects:Item[],scale:number) {
  const outline=footprint(item,scale);
  const overlaps=objects.filter(other=>other.id!==item.id&&intersects(outline,footprint(other,scale)));
  const swing:Pt[][]=[], clearance:Pt[][]=[];
  const nodes=nodeMap(plan);
  for(const door of plan.openings){
    if(door.kind!=="door"||door.status!=="confirmed"||!door.hostWallId||door.sillM>.02)continue;
    const ends=openingEnds(plan,door,nodes);
    if(!ends)continue;
    const [a,b]=ends;
    const length=Math.hypot(b.x-a.x,b.y-a.y);
    if(length<=0)continue;
    const angle=Math.atan2(b.y-a.y,b.x-a.x);
    if(door.swing){
      const hinge=door.hinge==="end"?b:a;
      const start=angle+(door.hinge==="end"?Math.PI:0);
      const end=angle+(door.swing==="left"?1:-1)*Math.PI/2;
      const sweep=Math.atan2(Math.sin(end-start),Math.cos(end-start));
      const sector=[hinge,...Array.from({length:13},(_,i)=>{
        const theta=start+sweep*i/12;
        return {x:hinge.x+Math.cos(theta)*length,y:hinge.y+Math.sin(theta)*length};
      })];
      if(intersects(outline,sector))swing.push(sector);
    }
    // Check a 60 cm central route through the doorway and 60 cm
    // of approach on either side. This is a local fit hint.
    const along=Math.min(length/2,.3/scale), across=.6/scale;
    const center={x:(a.x+b.x)/2,y:(a.y+b.y)/2};
    const zone=[[-1,-1],[1,-1],[1,1],[-1,1]].map(([u,v])=>({
      x:center.x+u*along*Math.cos(angle)-v*across*Math.sin(angle),
      y:center.y+u*along*Math.sin(angle)+v*across*Math.cos(angle),
    }));
    if(intersects(outline,zone))clearance.push(zone);
  }
  const room=roomsOf(plan).find(({polygon})=>contains(item.position,polygon));
  const neighbors=objects.filter(other=>other.id!==item.id&&!overlaps.includes(other))
    .map(other=>({polygon:footprint(other,scale),interior:false}));
  if(room)neighbors.push({polygon:room.polygon,interior:true});
  const narrow=tightGaps(outline,neighbors,scale);
  return {overlaps,swing,clearance,narrow};
}
