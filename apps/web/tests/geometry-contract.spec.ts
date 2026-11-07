import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {resolve} from 'node:path';
import type {PlanModel} from '../lib/plan/model';
import {withDerived,metersPerPixel} from '../lib/plan/derive';
import {wallPieces} from '../lib/plan/mesh';
import {moveNode,deleteWall,addWall} from '../lib/plan/ops';
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
