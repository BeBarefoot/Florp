import type { PlanModel, Pt, Wall } from "./model";
import type { Scene, View } from "./scene";

const corners = [[0,0],[640,0],[1000,0],[1000,680],[640,680],[0,680]];
const nodes = corners.map(([x,y],i)=>({id:String(i),x,y}));
const walls: Wall[] = [[0,1],[1,2],[2,3],[3,4],[4,5],[5,0],[1,4]].map(([a,b],i)=>({
  id:String(i),a:String(a),b:String(b),heightM:2.8,thicknessPx:14,material:"block",
  exterior:i<6,confidence:1,source:"user",
}));
function room(id:string,label:string,points:number[]){
  const polygon=points.map(i=>nodes[i]);
  return {id,label,polygon,areaPx2:Math.abs(polygon.reduce((a,p,i)=>{const n=polygon[(i+1)%polygon.length];return a+p.x*n.y-n.x*p.y;},0))/2,wallIds:[]};
}
export const samplePlan:PlanModel={
  schemaVersion:2,id:"sample",revision:1,imageTransform:{width:1000,height:680,rotation:0},
  scale:{metersPerPixel:.01,reference:{p1:nodes[0],p2:nodes[1],lengthMeters:6.4}},nodes,walls,
  rooms:[room("living","Living room",[0,1,4,5]),room("bedroom","Bedroom",[1,2,3,4])],
  openings:[[0,330,265],[1,65,200],[2,185,300],[5,150,320],[6,395,110]].map(([wall,offset,width],i)=>({
    id:"opening-"+i,kind:i===4?"door":"window",hostWallId:String(wall),offsetPx:offset,widthPx:width,
    span:null,heightM:i===4?2.2:1.65,sillM:i===4?0:.75,swing:null,hinge:"start",status:"confirmed",confidence:1})),
  findings:[],dismissedFindings:[],notes:[],
};
function stop(id:string,name:string,position:Pt,yaw:number):View{
  return {id,name,position,yaw,pitch:-9,horizontalFov:85,eyeHeight:1.58};
}
export const sampleScene:Scene={floorFinish:"oak",style:"",closedDoorIds:[],
  objects:[{id:"bed",kind:"bed",position:{x:815,y:155},width:2,depth:2.4,height:1.05,rotation:0},
    {id:"closet",kind:"wardrobe",position:{x:935,y:530},width:1.8,depth:.7,height:2.2,rotation:90}],
  views:[stop("lounge","Living room",{x:514,y:347},-145),stop("dining","Dining corner",{x:125,y:375},18),
    stop("suite","Bedroom",{x:735,y:545},-72)]};
