import { X } from "lucide-react";
import { useEffect, useState } from "react";
import type { Room } from "../../lib/plan/model";
import type { FloorMaterial } from "../../lib/plan/scene";
import { materialDefaults } from "../../lib/plan/floorMaterials";

const presets = [
  {name:"Warm wood", kind:"wood"},
  {name:"Light neutral", kind:"marble"},
  {name:"Modern concrete", kind:"concrete"},
] as const;

function DimensionField({label,metres,onChange}:{label:string;metres:number;onChange:(metres:number)=>void}){
  const [value,setValue]=useState(String(metres*100));
  useEffect(()=>{
    setValue(current=>Number(current)/100===metres?current:String(Math.round(metres*10000)/100));
  },[metres]);
  return <label>{label}<input type="number" min="5" max="500" step="1" required value={value}
    onChange={e=>{
      setValue(e.target.value);
      if(e.target.validity.valid)onChange(Number(e.target.value)/100);
    }}/></label>;
}

export default function FinishSheet({rooms,scope,selectScope,material,change,onPick,onClose,onSave,onReset,saving,dirty,notice,canPersist}:{
  rooms:Pick<Room,"id"|"label">[]; scope:string; selectScope:(id:string)=>void;
  material:FloorMaterial; change:(material:FloorMaterial)=>void;
  onPick:()=>void; onClose:()=>void; onSave:()=>void; onReset?:()=>void;
  saving:boolean; dirty:boolean; notice:string; canPersist:boolean;
}){
  return <section className="finish-sheet" aria-label="Floor finishes">
    <div className="finish-heading">
      <h2>Floor finishes</h2>
      <button type="button" onClick={onClose} disabled={saving} aria-label="Close finishes"><X size={20}/></button>
    </div>
    <fieldset disabled={saving}>
      <div className="finish-fields">
        <label>Apply to <select value={scope} onChange={e=>selectScope(e.target.value)}>
          <option value="">Whole floor</option>
          {rooms.map((room,i)=><option key={room.id} value={room.id}>{room.label||`Room ${i+1}`}</option>)}
        </select></label>
        <button type="button" onClick={onPick}>Pick on model</button>
      </div>
      <div className="finish-presets" aria-label="Starter palettes">
        {presets.map(({name,kind})=><button key={kind} type="button" onClick={()=>change(materialDefaults[kind])}>
          <span style={{background:materialDefaults[kind].color}}/>{name}
        </button>)}
      </div>
      <form onSubmit={e=>{
        e.preventDefault();
        onSave();
      }}>
        <div className="finish-fields">
          <label>Material <select value={material.kind} onChange={e=>change(materialDefaults[e.target.value as FloorMaterial["kind"]])}>
            <option value="wood">Wood</option><option value="concrete">Concrete</option>
            <option value="marble">Marble</option><option value="tile">Tile</option>
          </select></label>
          <label>Colour <input type="color" value={material.color} onChange={e=>change({...material,color:e.target.value})}/></label>
        </div>
        {material.kind!=="concrete"&&<div className="finish-fields">
          <DimensionField key={scope+material.kind+"width"} label={material.kind==="wood"?"Plank width (cm)":"Tile width (cm)"}
            metres={material.widthM} onChange={widthM=>change({...material,widthM})}/>
          <DimensionField key={scope+material.kind+"length"} label={material.kind==="wood"?"Plank length (cm)":"Tile length (cm)"}
            metres={material.lengthM} onChange={lengthM=>change({...material,lengthM})}/>
        </div>}
        <div className="finish-fields">
          {onReset&&<button type="button" onClick={onReset}>Use whole-floor finish</button>}
          <button type="submit" className="finish-save" disabled={!dirty}>{canPersist?"Save finishes":"Apply for this session"}</button>
        </div>
      </form>
    </fieldset>
    {notice&&<p role="status">{notice}</p>}
  </section>;
}
