import { metersPerPixel } from "./derive";
import type { PlanModel } from "./model";
import type { Scene, View } from "./scene";
import { findWalkStart, walkSpace } from "./walkSpace";

type Version = { plan:PlanModel; scene:Scene };
export type VariantSummary = {id:string;sourceId:string;title:string;planRevision:number;sceneRevision:number;
  metrics:{passage:number;storageDepth:number;moved:number}};
export type VariantComparison = VariantSummary & {baseline:Version;variant:Version};

export function commonView(baseline:Version, variant:Version):View|null {
  const a=metersPerPixel(baseline.plan), b=metersPerPixel(variant.plan);
  if(!a||!b)return null;
  for(const view of baseline.scene.views){
    if(walkSpace(baseline.plan,a,baseline.scene,view.eyeHeight).validCamera(view.position,true)&&
       walkSpace(variant.plan,b,variant.scene,view.eyeHeight).validCamera(view.position,true))return view;
  }
  const ground=walkSpace(baseline.plan,a,baseline.scene), proposed=walkSpace(variant.plan,b,variant.scene);
  const start=findWalkStart(baseline.plan,a,(point,walking)=>
    ground.validCamera(point,walking)&&proposed.validCamera(point,walking));
  return start?{...start,id:"comparison",name:"Shared viewpoint",pitch:-7,horizontalFov:105,eyeHeight:1.6}:null;
}
