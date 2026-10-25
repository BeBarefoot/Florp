export const API=process.env.NEXT_PUBLIC_API_URL||'http://localhost:8000';
export type Pt={x:number;y:number};
export type Room={id:string;label:string;points:Pt[];confidence:number};
export type Wall={id:string;start:Pt;end:Pt;thickness_m:number;height_m:number;inferred:boolean};
export type Opening={id:string;source_detection_id?:string|null;kind:'door'|'window';wall_id:string;offset_m:number;width_m:number;height_m:number;sill_m:number;inferred:boolean};
export type Geometry={structure_reviewed?:boolean;scale_source?:'unknown'|'provisional_auto'|'user_confirmed';width_px:number;height_px:number;px_per_meter:number|null;rooms:Room[];walls:Wall[];openings:Opening[];warnings:string[]};
export type Project={id:string;title:string};
export type Blueprint={id:string;project_id:string;filename:string;width:number;height:number};
export type Layout={id:string;blueprint_id:string;version:number;verified:boolean;geometry:Geometry};
export async function request<T>(path:string,init?:RequestInit):Promise<T>{
 const res=await fetch(API+path,{...init,cache:'no-store'});
 if(!res.ok){
  const raw=await res.text();
  let message=raw.slice(0,300);
  try{
   const payload=JSON.parse(raw) as {detail?:string|{message?:string;issues?:string[]}|Array<{msg?:string}>};
   if(typeof payload.detail==='string')message=payload.detail;
   else if(Array.isArray(payload.detail))message=payload.detail.map(i=>i.msg||'Invalid input').join('; ');
   else if(payload.detail&&typeof payload.detail==='object'){
     message=[payload.detail.message,...(payload.detail.issues||[])].filter(Boolean).join(' — ');
   }
  }catch{}
  throw Error(`${res.status}: ${message.slice(0,600)}`);
 }
 return res.json();
}
