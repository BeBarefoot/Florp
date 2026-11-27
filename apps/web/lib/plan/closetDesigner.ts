import { metersPerPixel, nodeMap, openingEnds, wallEnds } from "./derive";
import { fitsFloor, furnitureFit } from "./furnitureFit";
import { addWall } from "./ops";
import type { PlanModel, Pt } from "./model";
import { contains, footprint, intersects, newItem, type Item, type Scene } from "./scene";
import { roomsOf } from "./walkSpace";

export type ClosetOption = {
  title:string; plan:PlanModel; scene:Scene; partition:[Pt,Pt]; storage:Item;
  passage:number; moved:number; doorKeepouts:Pt[][];
};

export function closetOptions(plan:PlanModel, scene:Scene, roomId:string, mayMove:boolean):ClosetOption[]{
  const scale=metersPerPixel(plan);
  const polygon=roomsOf(plan).find(room=>room.id===roomId)?.polygon;
  if(!scale||!polygon)return [];
  const edges=polygon.map((start,index)=>({start,end:polygon[(index+1)%polygon.length]}))
    .sort((a,b)=>Math.hypot(b.end.x-b.start.x,b.end.y-b.start.y)-Math.hypot(a.end.x-a.start.x,a.end.y-a.start.y));
  const nodes=nodeMap(plan);
  const walls=plan.walls.map(wall=>{
    const [a,b]=wallEnds(plan,wall,nodes);
    return footprint({id:wall.id,kind:"wardrobe",position:{x:(a.x+b.x)/2,y:(a.y+b.y)/2},
      width:Math.hypot(b.x-a.x,b.y-a.y)*scale,depth:wall.thicknessPx*scale,height:wall.heightM,
      rotation:Math.atan2(b.y-a.y,b.x-a.x)*180/Math.PI},scale);
  });
  const options:ClosetOption[]=[];
  for(const passage of [.92,1.08]){
    for(const {start,end} of edges){
      const length=Math.hypot(end.x-start.x,end.y-start.y)*scale;
      if(length<3.65)continue;
      const u={x:(end.x-start.x)*scale/length,y:(end.y-start.y)*scale/length};
      const midpoint={x:(start.x+end.x)/2,y:(start.y+end.y)/2};
      const sign=contains({x:midpoint.x-u.y*.2/scale,y:midpoint.y+u.x*.2/scale},polygon)?1:-1;
      const n={x:-u.y*sign,y:u.x*sign};
      const point=(x:number,y:number)=>({x:start.x+(u.x*x+n.x*y)/scale,y:start.y+(u.y*x+n.y*y)/scale});
      const run=Math.min(length-1.8,3.6), left=(length-run)/2, right=left+run;
      const depth=.60, setback=.16, wallThickness=.10;
      const partitionY=setback+depth+passage+wallThickness/2;
      const rotation=Math.atan2(u.y,u.x)*180/Math.PI;
      const corridor=newItem("wardrobe",point(length/2,(setback+partitionY+.08)/2));
      Object.assign(corridor,{width:run+1.55,depth:partitionY+.08-setback,rotation});
      if(!fitsFloor(plan,corridor,scale))continue;
      const zone=footprint(corridor,scale);
      if(zone.some(point=>!contains(point,polygon))||walls.some(wall=>intersects(zone,wall)))continue;
      const blocksWindow=plan.openings.some(opening=>{
        if(opening.kind!=="window"||opening.status==="rejected")return false;
        const ends=openingEnds(plan,opening);
        if(!ends)return false;
        const projection=ends.map(p=>({
          x:((p.x-start.x)*u.x+(p.y-start.y)*u.y)*scale,
          y:((p.x-start.x)*n.x+(p.y-start.y)*n.y)*scale,
        }));
        return projection.every(p=>Math.abs(p.y)<.42)&&Math.max(...projection.map(p=>p.x))>left&&
          Math.min(...projection.map(p=>p.x))<right;
      });
      if(blocksWindow)continue;
      const doorFit=furnitureFit(plan,corridor,[],scale);
      if(doorFit.swing.length||doorFit.clearance.length)continue;

      const storage={...newItem("wardrobe",point(length/2,setback+depth/2)),
        width:run,depth,rotation};
      const partition:[Pt,Pt]=[point(left,partitionY),point(right,partitionY)];
      if(options.some(option=>Math.hypot(option.storage.position.x-storage.position.x,
        option.storage.position.y-storage.position.y)*scale<.75&&option.passage===passage))continue;

      const affected=scene.objects.filter(item=>intersects(footprint(item,scale),zone));
      if(affected.some(item=>!contains(item.position,polygon))||scene.objects.length>=100)continue;
      if(affected.length&&!mayMove)continue;
      const objects=scene.objects.filter(item=>!affected.includes(item));
      let placed=0;
      for(const item of affected){
        let moved:Item|undefined;
        for(let y=partitionY+.36;y<=6&&!moved;y+=.27){
          for(let x=.5;x<length-.5&&!moved;x+=.27){
            const candidate={...item,position:point(x,y)};
            const area=footprint(candidate,scale);
            if(!area.every(p=>contains(p,polygon))||!fitsFloor(plan,candidate,scale)||intersects(area,zone)||
              objects.some(other=>intersects(area,footprint(other,scale))))continue;
            const fit=furnitureFit(plan,candidate,objects,scale);
            if(!fit.swing.length&&!fit.clearance.length)moved=candidate;
          }
        }
        if(moved){objects.push(moved);placed++;}
      }
      if(placed!==affected.length)continue;
      const next=addWall(plan,...partition,wallThickness/scale,1e-7);
      if(!next.wallId)continue;
      const doorKeepouts=plan.openings.flatMap(opening=>{
        if(opening.kind!=="door"||opening.status!=="confirmed"||!opening.swing)return [];
        const ends=openingEnds(plan,opening);
        if(!ends)return [];
        const [a,b]=opening.hinge==="end"?[ends[1],ends[0]]:ends;
        const radius=Math.hypot(b.x-a.x,b.y-a.y), start=Math.atan2(b.y-a.y,b.x-a.x);
        const sweep=(opening.swing==="left"?1:-1)*(opening.hinge==="end"?-1:1)*Math.PI/2;
        return [[a,...Array.from({length:9},(_,i)=>{
          const angle=start+sweep*i/8;
          return {x:a.x+Math.cos(angle)*radius,y:a.y+Math.sin(angle)*radius};
        })]];
      });
      options.push({title:options.length?"Closet option B":"Closet option A",plan:next.model,
        scene:{...scene,objects:[...objects,storage]},partition,storage,passage,moved:affected.length,doorKeepouts});
      if(options.length===2)return options;
    }
  }
  return options;
}
