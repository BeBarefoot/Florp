import type {Pt} from "./model";

export function twoFingerDelta(previous:Pt,next:Pt,other:Pt){
  const bx=previous.x-other.x, by=previous.y-other.y;
  const ax=next.x-other.x, ay=next.y-other.y;
  const before=Math.hypot(bx,by), after=Math.hypot(ax,ay);
  const separated=before>=12&&after>=12;
  return {
    x:(next.x-previous.x)/2, y:(next.y-previous.y)/2,
    twist:separated?Math.atan2(bx*ay-by*ax,bx*ax+by*ay):0,
    pinch:separated?after/before:1,
  };
}
