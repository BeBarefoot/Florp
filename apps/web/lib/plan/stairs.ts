import {BufferGeometry, Float32BufferAttribute, Path, Shape, Vector2} from "three";
import polygonClipping, {type Polygon, type Ring} from "polygon-clipping";
import {metersPerPixel} from "./derive";
import type {PlanModel, Pt} from "./model";
import {treadLevels} from "./stairLevels";

const ringOf=(polygon:Pt[]):Ring=>polygon.map(({x,y})=>[x,y]);
function shapeFromRings([exterior,...holes]:Polygon,scale:number){
  const vertices=(ring:Ring)=>ring.map(([x,y])=>new Vector2(x*scale,-y*scale));
  const shape=new Shape(vertices(exterior));
  shape.holes=holes.map(hole=>new Path(vertices(hole)));
  return shape;
}

export function roomSurfaces(polygon:Pt[],scale:number,cutouts:Pt[][]=[]){
  const subject:Polygon=[ringOf(polygon)];
  const areas=cutouts.length?polygonClipping.difference(subject,...cutouts.map(ring=>[ringOf(ring)] as Polygon)):[subject];
  return areas.map(area=>shapeFromRings(area,scale));
}

/** Viewer and GLB share tread footprints and floor-relative elevations. */
export function stairPieces(model: PlanModel) {
  const scale=metersPerPixel(model);
  if(!scale)return [];
  return (model.stairs??[]).map(stair=>{
    const treads=treadLevels(stair);
    const steps=treads.map(({polygon,elevation})=>{
      const shape=new Shape(polygon.map(({x,y})=>new Vector2(x*scale,-y*scale)));
      shape.closePath();
      const height=elevation>0?elevation:stair.riseM;
      return {shape,height,bottom:elevation-height};
    });
    const [first,...rest]=treads.filter(tread=>tread.elevation<0).map(tread=>[ringOf(tread.polygon)] as Polygon);
    const areas=first?polygonClipping.union(first,...rest):[];
    // Enclose the exposed opening down to the lowest visible tread. This gives
    // a single-floor model a visible stairwell without assuming the lower floor's layout.
    const bottom=Math.min(...treads.map(tread=>tread.elevation))-stair.riseM;
    const wells=areas.map(area=>{
      const vertices:number[]=[];
      for(const ring of area)for(let i=0;i<ring.length-1;i++){
        const [ax,az]=ring[i].map(n=>n*scale), [bx,bz]=ring[i+1].map(n=>n*scale);
        vertices.push(ax,0,az,bx,0,bz,ax,bottom,az,ax,bottom,az,bx,0,bz,bx,bottom,bz);
      }
      const walls=new BufferGeometry().setAttribute("position",new Float32BufferAttribute(vertices,3));
      walls.computeVertexNormals();
      return {shape:shapeFromRings(area,scale),bottom,walls};
    });
    return {id:stair.id,direction:stair.direction??"up",steps,wells};
  });
}
