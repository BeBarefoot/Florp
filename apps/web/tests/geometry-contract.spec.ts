import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import type {PlanModel} from '../lib/plan/model';
import {withDerived,metersPerPixel,wallFootprint,inset} from '../lib/plan/derive';
import {wallPieces} from '../lib/plan/mesh';
import {moveNode,deleteWall,addWall} from '../lib/plan/ops';
import {connectedWallFace} from '../lib/plan/wallFaces';
import {samplePlan} from '../lib/plan/showcaseSample';
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
