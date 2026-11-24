import {Move,RotateCcw,RotateCw,Trash2,X} from "lucide-react";
import Link from "next/link";
import {catalog,type Item,type ObjectKind} from "../../lib/plan/scene";

const furniture=["sofa","bed","table","wardrobe"] as const;
function name(kind:ObjectKind){return kind.charAt(0).toUpperCase()+kind.slice(1);}

export default function FurnishSheet({objects,selected,pending,previewReason,dirty,saving,message,issues,onAdd,onSelect,onMove,onRotate,onResize,onRemove,onClose,onSave,onCancelPick,edit}:{
  objects:Item[];selected?:Item;pending:string;previewReason?:string;dirty:boolean;saving:boolean;
  message:string;issues:string[];edit?:string;
  onAdd:(kind:ObjectKind)=>void;onSelect:(id:string)=>void;onMove:()=>void;
  onRotate:(degrees:number)=>void;onResize:(key:"width"|"depth"|"height",value:number)=>void;
  onRemove:()=>void;onCancelPick:()=>void;onClose:()=>void;onSave:()=>void;
}){
  return <section className="finish-sheet furnish-sheet" aria-label="Furnish">
    <div className="finish-heading">
      <h2>Furnish</h2>
      <button type="button" aria-label={dirty?"Discard furniture changes":"Close Furnish"} disabled={saving} onClick={onClose}><X size={20}/></button>
    </div>
    {previewReason&&<p className="furnish-preview">{previewReason} {edit&&<Link href={edit+"?setup=furniture"}>Open the plan editor to enable saving.</Link>}</p>}
    <fieldset disabled={saving}>
      <div className="furnish-catalog" aria-label="Furniture catalog">
        {furniture.map(kind=><button key={kind} type="button" disabled={objects.length>=100} onClick={()=>onAdd(kind)}>
          <strong>{name(kind)}</strong><span>{catalog[kind].slice(0,2).map(m=>Math.round(m*100)).join(" × ")} cm</span>
        </button>)}
      </div>
      {objects.length>0&&<label className="furnish-select">Placed objects
        <select value={selected?.id??""} onChange={e=>onSelect(e.target.value)}>
          <option value="">Choose an object</option>
          {objects.map((item,i)=><option key={item.id} value={item.id}>{name(item.kind)} {i+1}</option>)}
        </select>
      </label>}
      {selected&&<fieldset disabled={!!pending}>
        <div className="furnish-dimensions">
          {(["width","depth","height"] as const).map(key=><label key={key}>{key.charAt(0).toUpperCase()+key.slice(1)} (cm)
            <input key={selected.id+selected[key]} type="number" min={6} max={key==="height"?500:800} step={1}
              defaultValue={Math.round(selected[key]*100)} onBlur={e=>{
                const cm=e.target.valueAsNumber;
                if(e.target.validity.valid&&Number.isFinite(cm)&&cm!==Math.round(selected[key]*100))onResize(key,cm/100);
                e.target.value=String(Math.round(selected[key]*100));
              }}/></label>)}
        </div>
        <div className="furnish-actions">
          <button onClick={onMove}><Move size={16}/>Move</button>
          <button aria-label="Rotate left 15 degrees" title="Rotate left 15°" onClick={()=>onRotate(-15)}><RotateCcw size={18}/></button>
          <button aria-label="Rotate right 15 degrees" title="Rotate right 15°" onClick={()=>onRotate(15)}><RotateCw size={18}/></button>
          <button aria-label="Remove object" onClick={onRemove}><Trash2 size={18}/></button>
        </div>
      </fieldset>}
      {pending&&<div className="finish-fields"><p role="status">{pending}</p><button type="button" onClick={onCancelPick}>Cancel pick</button></div>}
      {message&&<p role="status">{message}</p>}
      {issues.length>0&&<ul className="furnish-issues" aria-label="Fit warnings">{issues.map(issue=><li key={issue}>{issue}</li>)}</ul>}
      <button type="button" className="finish-save" disabled={!dirty||!!pending} onClick={onSave}>{previewReason?"Keep preview":"Save furniture"}</button>
    </fieldset>
    {edit&&!previewReason&&!dirty&&!pending&&!saving&&<p><Link href={edit+"?setup=furniture"}>Open 2D placement editor</Link></p>}
  </section>;
}
