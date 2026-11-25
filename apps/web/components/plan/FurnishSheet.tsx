import {Armchair,Bath,BedDouble,CookingPot,Move,RotateCcw,RotateCw,Trash2,TreePine,X} from "lucide-react";
import Link from "next/link";
import {useLayoutEffect,useRef,useState} from "react";
import {dimensions,furnitureRooms,objectName,tvInches,tvSizeRange,type ObjectKind} from "../../lib/plan/furnitureCatalog";
import type {Item} from "../../lib/plan/scene";
import {scrollTourRail} from "./scrollTourRail";

const roomIcons=[Armchair,BedDouble,Bath,CookingPot,TreePine];

export default function FurnishSheet({objects,selected,pending,previewReason,dirty,saving,message,issues,onAdd,onDragStart,onDragEnd,onSelect,onMove,onRotate,onResize,onScreenSize,onRemove,onClose,onSave,edit}:{
  objects:Item[];selected?:Item;pending:Item|null;previewReason?:string;dirty:boolean;saving:boolean;
  message:string;issues:string[];edit?:string;
  onAdd:(kind:ObjectKind)=>void;onSelect:(id:string)=>void;onMove:()=>void;
  onDragStart:(kind:ObjectKind)=>void;onDragEnd:()=>void;
  onRotate:(degrees:number)=>void;onResize:(key:"width"|"depth"|"height",value:number)=>void;
  onScreenSize:(inches:number)=>void;
  onRemove:()=>void;onClose:()=>void;onSave:()=>void;
}){
  const [roomIndex,setRoomIndex]=useState(0);
  const room=furnitureRooms[roomIndex];
  const catalog=useRef<HTMLDivElement>(null);
  const editFields=useRef<HTMLFieldSetElement>(null);
  const selectedId=selected?.id;
  const moving=!!pending&&pending.id===selectedId;
  useLayoutEffect(()=>{
    if(selectedId)editFields.current?.scrollIntoView({block:"nearest",inline:"nearest"});
  },[selectedId]);
  useLayoutEffect(()=>{if(catalog.current)catalog.current.scrollLeft=0;},[roomIndex]);
  return <section className="finish-sheet furnish-sheet" aria-label="Furnish" data-tour-tools onWheel={scrollTourRail}>
    <fieldset disabled={saving} className="furnish-body">
    <div className="finish-heading">
      <h2>Furnish</h2>
      <div className="furnish-rooms tour-rail" role="group" aria-label="Furniture rooms">
        {furnitureRooms.map(({name},index)=>{
          const Icon=roomIcons[index];
          return <button key={name} type="button" aria-pressed={index===roomIndex} onClick={()=>setRoomIndex(index)}>
            <Icon size={17} aria-hidden/>{name}
          </button>;
        })}
      </div>
      <button type="button" className="finish-close" aria-label={dirty?"Discard furniture changes":"Close Furnish"} onClick={onClose}><X size={20}/></button>
    </div>
    <div ref={catalog} className="furnish-items tour-rail" role="group" aria-label="Furniture catalog">
      {room.groups.map(group=><section key={group.name} className="furnish-group" aria-label={group.name}>
        <div className="furnish-catalog">
          {group.items.map(kind=>{
            const {width,depth}=dimensions(kind);
            return <button key={kind} type="button" disabled={objects.length>=100} draggable={!saving&&objects.length<100}
              aria-pressed={!moving&&pending?.kind===kind}
              onClick={()=>onAdd(kind)}
              onDragStart={event=>{
                event.dataTransfer.setData("application/x-florp-furniture",kind);
                event.dataTransfer.effectAllowed="copy";
                onDragStart(kind);
              }}
              onDragEnd={onDragEnd}>
              <strong>{objectName(kind)}</strong>
              <span>{kind==="tv"?"55″":`${Math.round(width*100)} × ${Math.round(depth*100)} cm`}</span>
            </button>;
          })}
        </div>
      </section>)}
    </div>
    <div className="furnish-footer">
      {objects.length>0&&
        <select className="furnish-select" aria-label="Placed objects" value={selected?.id??""} onChange={e=>onSelect(e.target.value)}>
          <option value="">Objects</option>
          {objects.map((item,i)=><option key={item.id} value={item.id}>{objectName(item.kind)} {i+1}</option>)}
        </select>}
      <div className="tour-rail furnish-edit-rail" role="group" aria-label="Furniture controls">
      {selected&&<fieldset className="furnish-edit-fields" ref={editFields}>
        <fieldset className="furnish-dimensions" disabled={moving}>
          {selected.kind==="tv"&&<label>Screen diagonal (inches)
            <input key={selected.id+selected.width} type="number" {...tvSizeRange} step={1}
              defaultValue={tvInches(selected.width,selected.height)}
              onKeyDown={event=>{if(event.key==="Enter")event.currentTarget.blur();}}
              onBlur={event=>{
                const inches=event.currentTarget.valueAsNumber;
                const previous=tvInches(selected.width,selected.height);
                if(event.currentTarget.validity.valid&&Number.isFinite(inches)&&inches!==previous)onScreenSize(inches);
                event.currentTarget.value=String(previous);
              }}/>
          </label>}
          {(selected.kind==="tv"?["depth"] as const:["width","depth","height"] as const).map(key=>{
            const thin=selected.kind==="rug"&&key==="height";
            const precision=thin?10:1;
            const cm=Math.round(selected[key]*100*precision)/precision;
            return <label key={key}>{key.charAt(0).toUpperCase()+key.slice(1)} (cm)
            <input key={selected.id+selected[key]} type="number" min={thin?.6:6}
              max={key==="height"?500:800} step={thin?.1:1}
              onKeyDown={event=>{if(event.key==="Enter")event.currentTarget.blur();}}
              defaultValue={cm} onBlur={e=>{
                const value=e.target.valueAsNumber;
                if(e.target.validity.valid&&Number.isFinite(value)&&value!==cm)onResize(key,value/100);
                e.target.value=String(cm);
              }}/></label>;
          })}
        </fieldset>
        <div className="furnish-actions">
          <button aria-label="Move" aria-pressed={moving} title="Move" onClick={onMove}><Move size={16}/></button>
          <button aria-label="Rotate left 15 degrees" title="Rotate left 15°" disabled={moving} onClick={()=>onRotate(-15)}><RotateCcw size={18}/></button>
          <button aria-label="Rotate right 15 degrees" title="Rotate right 15°" disabled={moving} onClick={()=>onRotate(15)}><RotateCw size={18}/></button>
          <button aria-label="Remove object" onClick={onRemove}><Trash2 size={18}/></button>
        </div>
      </fieldset>}
      {previewReason&&(edit?
        <Link className="furnish-preview" href={edit+"?setup=furniture"} title={previewReason}>Preview only</Link>:
        <span className="furnish-preview" title={previewReason}>Preview only</span>)}
      </div>
      <button type="button" className="finish-save" aria-label={previewReason?"Keep preview":"Save furniture"}
        disabled={!dirty||!!pending} onClick={onSave}>{previewReason?"Keep":"Save"}</button>
    </div>
    </fieldset>
    {(message||issues.length>0)&&<div className="tour-rail finish-notes">
      {message&&<p role="status">{message}</p>}
      {issues.length>0&&<ul className="furnish-issues" aria-label="Fit warnings">{issues.map(issue=><li key={issue}>{issue}</li>)}</ul>}
    </div>}
  </section>;
}
