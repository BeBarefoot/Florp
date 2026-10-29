'use client';
import type {Geometry,Pt} from '../lib/api';
export type RoomFace={id:string;points:Pt[];source_wall_ids:string[];shared_source_wall_ids:string[];verified:false};
export type LooseEndpoint={id:string;point:Pt;source_wall_ids:string[]};
export type SpatialQuality={room_faces?:RoomFace[];loose_endpoints?:LooseEndpoint[];structural_issues:string[];metric_issues:string[];ready_for_metric_scene:boolean};
export function SpatialOverlay({quality,roomId,onRoom,onGap,width}:{quality:SpatialQuality|null;roomId:string|null;onRoom:(id:string)=>void;onGap:(gap:LooseEndpoint)=>void;width:number}){
 return <>
 {(quality?.room_faces||[]).map((room,i)=><polygon key={room.id} points={room.points.map(p=>`${p.x},${p.y}`).join(' ')}
  fill={room.id===roomId?'#d99a2d':'#0b876d'} fillOpacity={room.id===roomId?.28:.10} stroke={room.id===roomId?'#b7791f':'#0b876d'} strokeWidth={width/500}
  role="button" tabIndex={0} aria-label={`Review room region ${i+1}`} style={{cursor:'pointer'}}
  onClick={e=>{e.stopPropagation();onRoom(room.id)}} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onRoom(room.id)}}}><title>Enclosed region {i+1} — needs source review</title></polygon>)}
 {(quality?.loose_endpoints||[]).map((gap,i)=><circle key={gap.id} cx={gap.point.x} cy={gap.point.y} r={Math.max(5,width/150)} fill="#f59e0b" stroke="white" strokeWidth={1.5}
  role="button" tabIndex={0} aria-label={`Review loose endpoint ${i+1}`} style={{cursor:'pointer'}}
  onClick={e=>{e.stopPropagation();onGap(gap)}} onKeyDown={e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();onGap(gap)}}}><title>Loose endpoint — inspect source before connecting</title></circle>)}
 </>;
}
export function SpatialInspector({quality,geometry,roomId,wallId,onBoundary,onPartition,onDraw,onNextGap}:{quality:SpatialQuality|null;geometry:Geometry;roomId:string|null;wallId:string|null;onBoundary:(id:string)=>void;onPartition:(id:string)=>void;onDraw:()=>void;onNextGap:()=>void}){
 const room=quality?.room_faces?.find(r=>r.id===roomId),wall=geometry.walls.find(w=>w.id===wallId);
 return <div className="stack">
 <strong>Rooms & gaps</strong>
 {!quality?<small>Checking the current draft…</small>:<small>{quality.room_faces?.length||0} enclosed regions · {quality.loose_endpoints?.length||0} loose endpoints</small>}
 <small>Select a shaded region or amber endpoint on the plan. Enclosed regions still need visual review; open boundaries are not rooms.</small>
 <button className="secondary" disabled={!quality?.loose_endpoints?.length} onClick={onNextGap}>Next loose endpoint</button>
 {wall&&<section className="stack"><strong>Selected boundary</strong><small>{wall.id}</small><small>Drag its green handles. Shared endpoints move together; hosted openings are protected.</small></section>}
 {room&&<section className="stack"><strong>Selected enclosed region</strong>
 <small>Choose a boundary to edit it directly on the drawing.</small>
 {room.source_wall_ids.map((id,i)=><button key={id} className="secondary" aria-pressed={wallId===id} onClick={()=>onBoundary(id)}>Boundary {i+1}{room.shared_source_wall_ids.includes(id)?' · shared partition':''}</button>)}
 <button className="secondary" onClick={onDraw}>Draw partition in this region</button>
 {room.shared_source_wall_ids.map(id=><button key={id} className="secondary" disabled={geometry.openings.some(o=>o.wall_id===id)}
  title={geometry.openings.some(o=>o.wall_id===id)?'Reconcile hosted openings before removing this partition':undefined}
  onClick={()=>onPartition(id)}>Remove shared partition {room.source_wall_ids.indexOf(id)+1}</button>)}
 <small>Partition changes affect only the unsaved draft. Undo restores them.</small>
 </section>}
 </div>;
}
