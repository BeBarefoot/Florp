import {Path,Shape,Vector2} from "three";
import type {PlanModel} from "./model";
import {metersPerPixel} from "./derive";

export function yardAreas(model:PlanModel) {
  const {width,height}=model.imageTransform;
  const mapRing=(ring:[number,number][])=>ring.map(([x,y])=>({x:x*width,y:y*height}));
  return (model.gardens??[]).map(region=>({
    polygon:mapRing(region.points),
    holes:(region.holes??[]).map(mapRing),
    surface:region.surface??("lawn" as const),
  }));
}

export function yardShapes(model:PlanModel) {
  const scale=metersPerPixel(model);
  if(!scale)return [];
  const vertices=(ring:ReturnType<typeof yardAreas>[number]["polygon"])=>ring.map(({x,y})=>new Vector2(x*scale,-y*scale));
  return yardAreas(model).map(region=>{
    const shape=new Shape(vertices(region.polygon));
    shape.holes=region.holes.map(ring=>new Path(vertices(ring)));
    return {shape,surface:region.surface};
  });
}

export const yardColor={lawn:"#839768",paving:"#b39b7c"} as const;
