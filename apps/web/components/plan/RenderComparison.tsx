"use client";
import { useState } from "react";

type ReferenceAsset = "preview.png" | "depth.png" | "mask.png";
type Size = [number,number];

export default function RenderComparison({asset}:{asset:(name:string)=>string}){
  const [overlay,setOverlay]=useState(false);
  const [opacity,setOpacity]=useState(55);
  const [reference,setReference]=useState<ReferenceAsset>("preview.png");
  const [referenceSize,setReferenceSize]=useState<Size|null>(null);
  const [resultSize,setResultSize]=useState<Size|null>(null);
  const boundsDiffer=referenceSize&&resultSize&&
    (referenceSize[0]!==resultSize[0]||referenceSize[1]!==resultSize[1]);
  return <div className="scene-render-review" role="group" aria-label="Render comparison">
    <div className="scene-actions">
      <button onClick={()=>setOverlay(!overlay)}>{overlay?"Side by side":"Overlay"}</button>
      <label>Reference layer <select value={reference} onChange={e=>{
        setReferenceSize(null);
        setReference(e.target.value as ReferenceAsset);
      }}>
        <option value="preview.png">Measured capture</option>
        <option value="depth.png">Depth</option>
        <option value="mask.png">Object and wall mask</option>
      </select></label>
      {overlay&&<label>Design opacity <input type="range" min="0" max="100"
        value={opacity} onChange={e=>setOpacity(Number(e.target.value))}/> {opacity}%</label>}
    </div>
    {boundsDiffer&&<p role="status">The images have different frame sizes. Check framing before comparing edges.</p>}
    <p>Compare the window, doorway and wall edges against the measured capture.</p>
    <div className={overlay?"scene-compare overlay":"scene-compare"}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={asset(reference)} alt={reference==="preview.png"?"Measured scene capture":reference==="depth.png"?"Captured depth":"Captured object and wall mask"}
        onLoad={e=>setReferenceSize([e.currentTarget.naturalWidth,e.currentTarget.naturalHeight])}/>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={asset("result.png")} alt="Generated design visualisation"
        style={overlay?{opacity:opacity/100}:undefined}
        onLoad={e=>setResultSize([e.currentTarget.naturalWidth,e.currentTarget.naturalHeight])}/>
    </div>
    <a href={asset("result.png")} target="_blank" rel="noreferrer">Open image</a>
  </div>;
}
