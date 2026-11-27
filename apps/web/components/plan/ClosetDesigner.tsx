import { useState } from "react";
import { closetOptions, type ClosetOption } from "../../lib/plan/closetDesigner";
import { metersPerPixel, nodeMap, wallEnds } from "../../lib/plan/derive";
import type { PlanModel, Pt } from "../../lib/plan/model";
import { footprint, type Scene } from "../../lib/plan/scene";
import { roomsOf } from "../../lib/plan/walkSpace";

const points=(poly:Pt[])=>poly.map(p=>`${p.x},${p.y}`).join(" ");

export function ClosetDrawing({original,option}: {original:PlanModel;option:ClosetOption}) {
  const nodes=nodeMap(original), scale=metersPerPixel(original)!;
  const storage=footprint(option.storage,scale);
  const padding=1.4/scale;
  const left=Math.max(0,Math.min(...storage.map(p=>p.x))-padding);
  const top=Math.max(0,Math.min(...storage.map(p=>p.y))-padding);
  const right=Math.min(original.imageTransform.width,Math.max(...storage.map(p=>p.x))+padding);
  const bottom=Math.min(original.imageTransform.height,Math.max(...storage.map(p=>p.y))+padding);
  const [a,b]=option.partition;
  return <svg aria-label="Closet layout with existing door swings" role="img"
    viewBox={`${left} ${top} ${right-left} ${bottom-top}`}>
    {original.walls.map(wall=>{
      const [a,b]=wallEnds(original,wall,nodes);
      return <line key={wall.id} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#535e52" strokeWidth={wall.thicknessPx}/>;
    })}
    {option.doorKeepouts.map((polygon,index)=><polygon key={index} fill="#e9c1a6" opacity=".6" points={points(polygon)}/>)}
    <polygon fill="#b9cdbb" stroke="#375847" strokeWidth=".02" vectorEffect="non-scaling-stroke" points={points(storage)}/>
    <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#375847" strokeWidth={.1/scale}/>
  </svg>;
}

export default function ClosetDesigner({plan,scene,disabled,open}: {plan:PlanModel;scene:Scene;disabled:boolean;open:boolean}) {
  const [roomId,setRoomId]=useState("");
  const [partition,setPartition]=useState(false);
  const [move,setMove]=useState(false);
  const [result,setResult]=useState<{options:ClosetOption[];plan:PlanModel;scene:Scene}|null>(null);
  const rooms=roomsOf(plan);
  const options=result?.plan===plan&&result.scene===scene?result.options:null;
  const clear=()=>setResult(null);
  return <details open={open||undefined} className="scene-change-review closet-designer">
    <summary>Closet Designer</summary>
    <p>Add a walk-through closet with two open ends. Existing walls, windows, and doors are fixed in these proposals.</p>
    <div className="scene-actions">
      <label>Room <select value={roomId} onChange={event=>{setRoomId(event.target.value);clear();}}>
        <option value="">Choose a room</option>
        {rooms.map((room,index)=><option key={room.id} value={room.id}>{room.label??`Room ${index+1}`}</option>)}
      </select></label>
      <label><input type="checkbox" checked={partition} onChange={event=>{setPartition(event.target.checked);clear();}}/> A new lightweight partition is possible</label>
      <label><input type="checkbox" checked={move} onChange={event=>{setMove(event.target.checked);clear();}}/> Furniture in this room can move</label>
      <button disabled={disabled||!roomId||!partition} onClick={()=>setResult({options:closetOptions(plan,scene,roomId,move),plan,scene})}>
        Suggest closet layouts
      </button>
    </div>
    {options?.length===0&&<p role="status">No layout fits with these constraints. Try a larger room or allow furniture to move.</p>}
    {options&&options.length>0&&<div className="closet-options">
      {options.map(option=><article key={option.title}>
        <h3>{option.title}</h3>
        <ClosetDrawing original={plan} option={option}/>
        <p>{Math.round(option.passage*100)} cm passage · {Math.round(option.storage.depth*100)} cm storage depth
          {option.moved>0&&` · ${option.moved} items moved`}</p>
      </article>)}
    </div>}
  </details>;
}
