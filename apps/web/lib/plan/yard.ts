import {Path,Shape,Vector2} from "three";
import type {PlanModel} from "./model";
import {metersPerPixel} from "./derive";

export function yardShapes(model:PlanModel) {
  const scale=metersPerPixel(model);
  if(!scale)return [];
  const {width,height}=model.imageTransform;
  const vertices=(ring:[number,number][])=>ring.map(([x,z])=>new Vector2(x*width*scale,-z*height*scale));
  return (model.gardens??[]).map(region=>{
    const shape=new Shape(vertices(region.points));
    shape.holes=(region.holes??[]).map(ring=>new Path(vertices(ring)));
    return shape;
  });
}
