import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import type {PlanModel} from '../lib/plan/model';
import {withDerived,metersPerPixel,wallFootprint,inset} from '../lib/plan/derive';
import {wallPieces} from '../lib/plan/mesh';
import {moveNode,deleteWall,addWall} from '../lib/plan/ops';
import {connectedWallFace} from '../lib/plan/wallFaces';
import {samplePlan} from '../lib/plan/showcaseSample';
import {housePlacement} from '../lib/plan/houseOverview';
import {sceneReview} from "../lib/plan/sceneReview";
import {closetOptions} from "../lib/plan/closetDesigner";
import {dimensions,objectName} from '../lib/plan/furnitureCatalog';
import {fitsFloor} from '../lib/plan/furnitureFit';
import {furnitureParts,makeFurnitureResources} from '../lib/plan/furnitureModels';

test('wall face continues past a partition on the opposite side only',()=>{
 const template=samplePlan.walls[0];
 const plan={...samplePlan,nodes:[
  {id:"n0",x:0,y:0},{id:"n1",x:200,y:0},{id:"n2",x:400,y:0},{id:"n3",x:200,y:100},
 ],walls:[
  {...template,id:"left",a:"n0",b:"n1"},
  {...template,id:"right",a:"n2",b:"n1"},
  {...template,id:"partition",a:"n1",b:"n3"},
 ]};
 expect(connectedWallFace(plan,{id:"left",side:"a"})).toEqual([{id:"left",side:"a"}]);
 expect(connectedWallFace(plan,{id:"left",side:"b"})).toEqual([{id:"left",side:"b"},{id:"right",side:"b"}]);
});

test('Vantage uses the garage footprint and renders four correctly oriented wheels',()=>{
 const car={id:"parking",kind:"car" as const,position:{x:320,y:340},rotation:0,...dimensions("car")};
 const garage={...samplePlan,rooms:[{...samplePlan.rooms[0],roomType:"garage" as const}]};
 expect(objectName(car.kind)).toBe("Aston Martin Vantage");
 expect(fitsFloor(garage,car,.01)).toBe(true);
 expect(fitsFloor(samplePlan,car,.01)).toBe(false);
 const parts=furnitureParts(car,"hotel");
 expect(parts.filter(part=>part.shape==="wheel"&&part.finish==="black")).toHaveLength(4);
 const resources=makeFurnitureResources();
 const tire=resources.geometry("wheel");
 tire.computeBoundingBox();
 expect(tire.boundingBox?.min.z).toBeCloseTo(-.5);
 expect(tire.boundingBox?.max.z).toBeCloseTo(.5);
 expect(resources.geometry("vantageBody").getAttribute("position").count).toBeGreaterThan(100);
 resources.dispose();
});

const cases=JSON.parse(readFileSync(resolve(process.cwd(),'../../tests/fixtures/geometry-contract.json'),'utf8')) as {name:string;model:PlanModel;expectedAreasPx2:number[];expectedBoundsPx:number[][]}[];
for(const c of cases)test(`shared geometry contract: ${c.name}`,()=>{
 const m=withDerived(c.model);
 expect(m.rooms.map(r=>r.areaPx2)).toEqual(c.expectedAreasPx2);
 expect(metersPerPixel(m)).toBe(.01);
 expect(m.rooms.map(r=>[Math.min(...r.polygon.map(p=>p.x)),Math.min(...r.polygon.map(p=>p.y)),
  Math.max(...r.polygon.map(p=>p.x)),Math.max(...r.polygon.map(p=>p.y))])).toEqual(c.expectedBoundsPx);
 const nodes=new Map(m.nodes.map(n=>[n.id,n]));
 for(const piece of wallPieces(m)){
  const wall=m.walls.find(w=>w.id===piece.id)!;
  const a=nodes.get(wall.a)!,b=nodes.get(wall.b)!;
  expect(piece.lengthM).toBeCloseTo(Math.hypot(b.x-a.x,b.y-a.y)*.01,9);
  expect(piece.thicknessM).toBeCloseTo(wall.thicknessPx*.01,9);
  for(const chunk of piece.chunks){expect(chunk.end).toBeGreaterThan(chunk.start);expect(chunk.high).toBeGreaterThan(chunk.low);}
 }
});
test('room adjustments retain unambiguous semantics and flag merge/split',()=>{
 const m=withDerived(structuredClone(cases[0].model));
 m.rooms[0]={...m.rooms[0],label:'Bedroom',roomType:'bedroom',ceilingHeightM:3.1};
 const moved=moveNode(m,'n1',{x:280,y:100});
 expect(moved.rooms[0]).toMatchObject({label:'Bedroom',roomType:'bedroom',ceilingHeightM:3.1});
 const merged=deleteWall(m,'w6');
 expect(merged.rooms).toHaveLength(1);
 expect(merged.rooms[0].needsSemanticReview).toBe(true);
 expect(merged.rooms[0].label).toBeNull();
 const split=addWall(m,{x:175,y:100},{x:175,y:300},10).model;
 expect(split.rooms).toHaveLength(3);
 expect(split.rooms.filter(r=>r.needsSemanticReview)).toHaveLength(2);
 expect(m.rooms[0].label).toBe('Bedroom');
});

test('scale check detects a compressed footprint and respects recalibration',()=>{
 const model=cases[0].model;
 expect(wallFootprint(model,null)).toBeNull();
 expect(wallFootprint(model,.001)?.unusuallySmall).toBe(true);
 expect(wallFootprint(model,.05)?.unusuallySmall).toBe(false);
});

test('nearly parallel walls of different thickness bevel the room inset',()=>{
 const fixture=JSON.parse(readFileSync(resolve(process.cwd(),'../../tests/fixtures/room-inset-contract.json'),'utf8'));
 const outline=inset(fixture.points,fixture.thickness);
 expect(outline).toHaveLength(6);
 const area=outline.reduce((sum,p,i)=>{
  const q=outline[(i+1)%outline.length];
  return sum+(p.x*q.y-q.x*p.y)/2;
 },0);
 expect(area).toBeCloseTo(fixture.expectedAreaPx2,7);
});

test("whole-house placement converts and rotates the upper drawing in ground-floor units", () => {
 const scene={views:[],objects:[],style:""};
 const upper={...samplePlan,scale:{...samplePlan.scale,reference:{
   ...samplePlan.scale.reference!,lengthMeters:samplePlan.scale.reference!.lengthMeters*2,
 }}};
 const placement=housePlacement({ground:{plan:samplePlan,scene},upper:{plan:upper,scene},provisionalOrder:false,
   alignment:{centerX:420,centerY:560,rotationDeg:90,scale:1.5}});
 expect(placement.center[0]).toBeCloseTo(4.2);
 expect(placement.center[1]).toBeCloseTo(2.8);
 expect(placement.center[2]).toBeCloseTo(5.6);
 expect(placement.upperCenter).toEqual([10,6.8]);
 expect(placement.horizontalScale).toBeCloseTo(.75);
 expect(placement.rotation).toBeCloseTo(Math.PI/2);
 expect(placement.span).toBeGreaterThan(11);
});

test("scene review finds a blocked view, an orphaned finish and a newly clipped object", async () => {
 const previous=samplePlan;
 const plan={...previous,revision:2,rooms:[{...previous.rooms[0],polygon:[{x:0,y:0},{x:250,y:0},{x:250,y:680},{x:0,y:680}]}],
  nodes:[...previous.nodes,{id:"new-a",x:300,y:80},{id:"new-b",x:300,y:650}],
  walls:[...previous.walls,{...previous.walls[0],id:"new-wall",a:"new-a",b:"new-b"}]};
 const scene:import("../lib/plan/scene").Scene={style:"",roomFloorMaterials:{bedroom:{kind:"wood",color:"#c1a27b",widthM:.18,lengthM:1.2}},
  objects:[{id:"bed",kind:"bed",position:{x:400,y:450},width:1.4,depth:1.7,height:1,rotation:0}],
  views:[{id:"view",name:"Living view",position:{x:300,y:100},yaw:0,pitch:0,horizontalFov:90,eyeHeight:1.6}]};
 expect(sceneReview(plan,previous,scene)).toEqual(expect.arrayContaining([
  expect.objectContaining({kind:"object",id:"bed"}),
  expect.objectContaining({kind:"view",id:"view"}),
  expect.objectContaining({kind:"room",id:"bedroom",missing:true}),
 ]));
});

test("closet designer keeps the baseline and offers two measured walk-through layouts", () => {
 const plan={...samplePlan,openings:[]};
 const scene:import("../lib/plan/scene").Scene={views:[],objects:[],style:""};
 const options=closetOptions(plan,scene,"living",false);
 expect(options).toHaveLength(2);
 for(const option of options){
  expect(option.plan.walls).toHaveLength(plan.walls.length+1);
  expect(option.plan.openings).toEqual(plan.openings);
  expect(option.passage).toBeGreaterThanOrEqual(.92);
  expect(option.storage.depth).toBe(.6);
 }
 expect(scene.objects).toHaveLength(0);
 expect(plan.walls).toHaveLength(samplePlan.walls.length);
});
