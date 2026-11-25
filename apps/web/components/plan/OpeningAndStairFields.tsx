import {metersPerPixel, wallEnds} from "../../lib/plan/derive";
import type {Opening, PlanModel, Stair, StairDirection, WindowFrame} from "../../lib/plan/model";
import {landingIndex} from "../../lib/plan/stairLevels";
import {windowFrameDefaults, windowFrameFor} from "../../lib/plan/windowStyle";

function NumericField({label,value,min,max,step,onChange}:{label:string;value:number;min:number;max:number;step:number;onChange:(n:number)=>void}){
  return <label>{label}<input key={value} type="number" min={min} max={max} step="any"
    inputMode={step===1?"numeric":"decimal"} defaultValue={value}
    onKeyDown={event=>{if(event.key==="Enter")event.currentTarget.blur();}}
    onBlur={event=>{
      const input=event.currentTarget;
      const n=input.valueAsNumber;
      if(input.validity.valid&&Number.isFinite(n)&&(step!==1||Number.isInteger(n))&&n!==value)onChange(n);
      input.value=String(value);
    }}/></label>;
}

const roundedM=(m:number)=>Number(m.toFixed(3));

export function WindowFields({model,opening,onPatch}:{model:PlanModel;opening:Opening;onPatch:(patch:Partial<Opening>)=>void}){
  const wall=model.walls.find(w=>w.id===opening.hostWallId);
  const scale=metersPerPixel(model);
  const frame=windowFrameFor(opening);
  const hostHeight=wall?.heightM??(opening.heightM+opening.sillM);
  function setFrame(patch:Partial<WindowFrame>){onPatch({windowFrame:{...frame,...patch}});}
  const span=wall&&wallEnds(model,wall);
  const maxWidth=span&&scale?Math.hypot(span[1].x-span[0].x,span[1].y-span[0].y)*scale:0;
  return <div className="opening-stair-fields">
    {scale&&wall&&<NumericField label="Window width (m)" value={roundedM(opening.widthPx*scale)} min={scale} max={maxWidth} step={.01}
      onChange={width=>{
        const widthPx=width/scale;
        onPatch({widthPx,offsetPx:opening.offsetPx+(opening.widthPx-widthPx)/2});
      }}/>}
    <NumericField label="Window height (m)" value={opening.heightM} min={.05} max={hostHeight-opening.sillM} step={.01}
      onChange={heightM=>onPatch({heightM})}/>
    <NumericField label="Sill height (m)" value={opening.sillM} min={0} max={Math.min(10,hostHeight-opening.heightM)} step={.01}
      onChange={sillM=>onPatch({sillM})}/>
    <label>Frame material<select value={frame.material} onChange={event=>{
      const material=event.target.value as WindowFrame["material"];
      setFrame({material,...(!opening.windowFrame||frame.color===windowFrameDefaults[frame.material]?{color:windowFrameDefaults[material]}:{})});
    }}>
      <option value="aluminium">Aluminium</option><option value="wood">Wood</option><option value="vinyl">Vinyl</option>
    </select></label>
    <label>Frame colour<input type="color" value={frame.color} onChange={e=>setFrame({color:e.target.value})}/></label>
    <NumericField label="Frame width (cm)" value={frame.widthM*100} min={2} max={15} step={.1}
      onChange={cm=>setFrame({widthM:cm/100})}/>
    <label>Glass panes<select value={frame.panes} onChange={event=>setFrame({panes:event.target.value==="2"?2:1})}>
      <option value={1}>One pane</option><option value={2}>Two panes</option>
    </select></label>
    {!scale&&<p className="fe-muted">Set scale to enter an exact window width.</p>}
  </div>;
}

export function StairFields({stair,onPatch}:{stair:Stair;onPatch:(patch:Partial<Stair>)=>void}){
  const direction=stair.direction??"up";
  return <div className="opening-stair-fields">
    <label>Stair direction<select value={direction} onChange={event=>{
      const direction=event.target.value as StairDirection;
      onPatch({direction,treadsBelow:direction==="both"?landingIndex(stair):null});
    }}>
      <option value="up">Up from this floor</option>
      <option value="down">Down from this floor</option>
      <option value="both">Up and down from a landing</option>
    </select></label>
    {direction==="both"&&<NumericField label="Treads below the landing" value={landingIndex(stair)} min={1} max={stair.treads.length-2} step={1}
      onChange={treadsBelow=>onPatch({treadsBelow})}/>}
    <NumericField label="Rise per step (m)" value={stair.riseM} min={.08} max={.3} step={.005}
      onChange={riseM=>onPatch({riseM})}/>
    <button type="button" onClick={()=>onPatch({treads:[...stair.treads].reverse(),
      ...(direction==="both"?{treadsBelow:stair.treads.length-1-landingIndex(stair)}:{})})}>Reverse direction</button>
  </div>;
}
