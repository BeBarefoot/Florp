import type {PlanModel, Stair} from "./model";

export function landingIndex(stair:Stair) {
  return Math.max(1,Math.min(stair.treads.length-2,stair.treadsBelow??Math.floor((stair.treads.length-1)/2)));
}

export function treadLevels(stair:Stair) {
  const direction=stair.direction??"up";
  const landing=landingIndex(stair);
  return stair.treads.map((polygon,index)=>({
    polygon, elevation:(direction==="both"?index-landing:direction==="down"?-index-1:index+1)*stair.riseM,
  }));
}

export function stairCutouts(model:PlanModel) {
  return (model.stairs??[]).flatMap(stair=>treadLevels(stair).filter(tread=>tread.elevation<0).map(tread=>tread.polygon));
}

export function stairHeadroom(model:PlanModel,ceilingHeight:number) {
  return (model.stairs??[]).flatMap(stair=>{
    const treads=treadLevels(stair);
    if(!treads.some(tread=>tread.elevation>=ceilingHeight-stair.riseM))return [];
    return treads.filter(tread=>tread.elevation>Math.max(0,ceilingHeight-1.95)).map(tread=>tread.polygon);
  });
}
