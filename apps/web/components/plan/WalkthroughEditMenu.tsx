import {useState, type FormEvent, type RefObject} from "react";
import {PaintRoller,RotateCw,Trash2,X} from "lucide-react";
import Link from "next/link";
import {objectName,tvDimensions,tvInches,tvSizeRange,type ObjectKind} from "../../lib/plan/furnitureCatalog";
import {newItem,type Item,type WallMaterial,type WindowFinish} from "../../lib/plan/scene";
import {windowFrameDefaults} from "../../lib/plan/windowStyle";

export type WalkEditor =
  | {kind:"object";item:Item;suggestion:boolean;alternatives:ObjectKind[];onApply:(item:Item)=>void;onRemove:()=>void}
  | {kind:"wall";finish:WallMaterial|null;color:string;onApply:(finish:WallMaterial|null)=>void}
  | {kind:"window";finish:WindowFinish;onApply:(finish:WindowFinish)=>void;onReset?:()=>void;href?:string}
  | {kind:"door";closed:boolean;onToggle:()=>void;href?:string};

function FurnitureFields({editor}:{editor:Extract<WalkEditor,{kind:"object"}>}){
  const [item,setItem]=useState(editor.item);
  const [changed,setChanged]=useState(false);
  const [removed,setRemoved]=useState(false);
  const isTV=item.kind==="tv";
  function apply(event:FormEvent<HTMLFormElement>){
    event.preventDefault();
    if(removed){editor.onRemove();return;}
    const data=new FormData(event.currentTarget);
    const next={...item,...(isTV?tvDimensions(Number(data.get("diagonal"))):{
      width:Number(data.get("width"))/100,height:Number(data.get("height"))/100,
    }),depth:Number(data.get("depth"))/100};
    if(next.mattressWidth!=null)next.mattressWidth=Math.min(next.width,next.mattressWidth);
    if(next.mattressDepth!=null)next.mattressDepth=Math.min(next.depth*.96,next.mattressDepth);
    editor.onApply(next);
  }
  return <form className="walk-edit-fields" onSubmit={apply} onChange={()=>setChanged(true)}>
    {!removed&&<div className="walk-edit-grid" key={item.kind}>
      {isTV&&<label>Screen (inches)<input name="diagonal" type="number" {...tvSizeRange} required step="1" defaultValue={tvInches(item.width,item.height)}/></label>}
      {(isTV?["depth"] as const:["width","depth","height"] as const).map(key=>{
        const thin=(item.kind==="rug"||item.kind==="cooktop")&&key==="height";
        return <label key={key}>{key[0].toUpperCase()+key.slice(1)} (cm)
          <input name={key} type="number" required min={thin?.6:6} max={key==="height"?500:800}
            step="any" defaultValue={Number((item[key]*100).toFixed(6))}/>
        </label>;
      })}
    </div>}
    <div className="walk-edit-actions">
      {removed?<button type="button" onClick={()=>setRemoved(false)}>Undo remove</button>:<>
        <button type="button" onClick={()=>{setItem({...item,rotation:(item.rotation+90)%360});setChanged(true);}}><RotateCw size={15} aria-hidden/>Rotate</button>
        {editor.alternatives.length>0&&<select aria-label="Replace object" value={item.kind===editor.item.kind?"":item.kind} onChange={event=>{
        setItem({...newItem(event.target.value as ObjectKind,item.position),id:item.id,rotation:item.rotation});
      }}>
        <option value={editor.item.kind}>{objectName(editor.item.kind)}</option>
        <option value="" disabled>Replace</option>
        {editor.alternatives.map(kind=><option key={kind} value={kind}>{objectName(kind)}</option>)}
      </select>}
        <button type="button" onClick={()=>setRemoved(true)}><Trash2 size={15} aria-hidden/>{editor.suggestion?"Hide":"Remove"}</button>
      </>}
      <button type="submit" disabled={!changed&&!removed&&!editor.suggestion}
        aria-label={editor.suggestion&&!removed?"Place detected object":"Save furniture"}>{editor.suggestion&&!removed?"Place":"Save"}</button>
    </div>
  </form>;
}

function WallFields({editor}:{editor:Extract<WalkEditor,{kind:"wall"}>}){
  const [kind,setKind]=useState<WallMaterial["kind"]|"">(editor.finish?.kind??"");
  const [color,setColor]=useState(editor.finish?.color??editor.color);
  return <form className="walk-edit-fields" onSubmit={event=>{event.preventDefault();editor.onApply(kind?{kind,color}:null);}}>
    <div className="walk-edit-grid">
      <label>Material<select value={kind} onChange={event=>setKind(event.target.value as typeof kind)}>
        <option value="">Default</option><option value="paint">Paint</option><option value="tile">Ceramic tile</option>
      </select></label>
      <label>Color<input type="color" value={color} onChange={event=>{setColor(event.target.value);if(!kind)setKind("paint");}}/></label>
    </div>
    <div className="walk-edit-actions"><button><PaintRoller size={15} aria-hidden/>Apply finish</button></div>
  </form>;
}

function WindowFields({editor}:{editor:Extract<WalkEditor,{kind:"window"}>}){
  const [finish,setFinish]=useState(editor.finish);
  return <form className="walk-edit-fields" onSubmit={event=>{event.preventDefault();editor.onApply(finish);}}>
    <div className="walk-edit-grid">
      <label>Frame material<select value={finish.material} onChange={event=>{
        const material=event.target.value as WindowFinish["material"];
        setFinish({material,color:windowFrameDefaults[material]});
      }}><option value="aluminium">Aluminium</option><option value="wood">Wood</option><option value="vinyl">Vinyl</option></select></label>
      <label>Frame color<input type="color" value={finish.color} onChange={event=>setFinish({...finish,color:event.target.value})}/></label>
    </div>
    <div className="walk-edit-actions">
      {editor.href&&<Link href={editor.href}>Dimensions</Link>}
      {editor.onReset&&<button type="button" onClick={editor.onReset}>Reset</button>}
      <button>Apply finish</button>
    </div>
  </form>;
}

export function WalkthroughEditMenu({editor,menu,busy,message,close}:{
  editor:WalkEditor;menu:RefObject<HTMLDivElement|null>;busy:boolean;message:string;close:()=>void;
}){
  const name=editor.kind==="object"?objectName(editor.item.kind):editor.kind[0].toUpperCase()+editor.kind.slice(1);
  return <div ref={menu} className="walk-object-tools" role="group" aria-label={name} data-tour-tools
    onKeyDown={event=>{if(event.key==="Escape"){event.stopPropagation();close();}}}>
    <header><strong>{name}</strong><button type="button" onClick={close} aria-label="Close object controls"><X size={16}/></button></header>
    <fieldset disabled={busy}>
      {editor.kind==="object"&&<FurnitureFields editor={editor}/>}
      {editor.kind==="wall"&&<WallFields editor={editor}/>}
      {editor.kind==="window"&&<WindowFields editor={editor}/>}
      {editor.kind==="door"&&<div className="walk-edit-actions">
        {editor.href&&<Link href={editor.href}>Edit opening</Link>}
        <button type="button" onClick={editor.onToggle}>{editor.closed?"Open door":"Close door"}</button>
      </div>}
    </fieldset>
    {message&&<p role="status">{message}</p>}
  </div>;
}
