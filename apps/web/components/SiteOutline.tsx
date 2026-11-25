import type {SiteRegion} from "../lib/api";

export function SiteOutline({region:r}:{region:SiteRegion}){
  const rings=[r.points,...(r.holes??[])];
  const garden=r.kind==="garden";
  const paved=r.surface==="paving";
  return <path data-site-region={r.kind} data-site-surface={r.surface??undefined} d={rings.map(ring=>"M"+ring.map(p=>p.join(",")).join(" L")+" Z").join(" ")}
    fillRule="evenodd" fill={paved?"#bd966c":garden?"#3d994a":"#de9219"} fillOpacity=".32" stroke={paved?"#8f6542":garden?"#247439":"#a85e00"}
    strokeWidth="2" vectorEffect="non-scaling-stroke"><title>{paved?"Patio":garden?"Lawn":"Stairs"}</title></path>;
}

export function regionArea(r:SiteRegion,width:number,height:number,scale:number){
  const area=(ring:[number,number][])=>Math.abs(ring.reduce((sum,[x,y],i)=>{
    const [nextX,nextY]=ring[(i+1)%ring.length];
    return sum+x*nextY-y*nextX;
  },0))/2;
  return (area(r.points)-(r.holes??[]).reduce((sum,ring)=>sum+area(ring),0))*width*height*scale*scale;
}
