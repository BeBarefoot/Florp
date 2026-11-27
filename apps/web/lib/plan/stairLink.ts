import type { Pt } from "./model";
import type { SiteRegion } from "../api";

export type StairLanding = Pt & { revision: number; yaw: number };

export function nearStairs(point: Pt, treads: Pt[][], regions: SiteRegion[], width: number, height: number, scale: number) {
  const outlines = [...treads, ...regions.filter(region => region.kind === "stairs")
    .map(region => region.points.map(([x,y]) => ({x:x*width,y:y*height})))];
  return outlines.some(outline => outline.some((a,index) => {
    const b = outline[(index+1)%outline.length];
    const dx=b.x-a.x, dy=b.y-a.y;
    const length=dx*dx+dy*dy;
    const t=length ? Math.max(0,Math.min(1,((point.x-a.x)*dx+(point.y-a.y)*dy)/length)) : 0;
    return Math.hypot(point.x-a.x-t*dx,point.y-a.y-t*dy)*scale <= 1.8;
  }));
}
