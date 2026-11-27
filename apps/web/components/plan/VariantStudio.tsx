"use client";

import { Canvas, useThree } from "@react-three/fiber";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { API, request } from "../../lib/api";
import { metersPerPixel } from "../../lib/plan/derive";
import { commonView, type VariantComparison } from "../../lib/plan/designVariants";
import type { View } from "../../lib/plan/scene";
import { walkSpace } from "../../lib/plan/walkSpace";
import DesktopBrand from "../DesktopBrand";
import { EyeCamera, SceneMesh } from "./SceneMesh";
import { WalkCamera } from "./WalkCamera";

function ComparisonScene({version,view,walking}: {version:VariantComparison["baseline"];view:View;walking:boolean}) {
  const {plan,scene}=version;
  const {size}=useThree();
  const pose=useRef<View|null>(null);
  const scale=metersPerPixel(plan)!;
  const clear=useMemo(()=>walkSpace(plan,scale,scene,view.eyeHeight),[plan,scale,scene,view.eyeHeight]);
  const frame=useMemo(()=>({width:Math.max(1,size.width),height:Math.max(1,size.height),configured:false,model:"",provider:""}),
    [size.width,size.height]);
  return <>
    <color attach="background" args={["#d4e3e9"]}/>
    <SceneMesh m={plan} objects={scene.objects} closedDoorIds={scene.closedDoorIds} floorStyle={scene}
      wallFinishes={scene.wallFinishes} windowFinishes={scene.windowFinishes} designPreset={scene.designPreset} presentation/>
    {walking?<WalkCamera view={view} scale={scale} frame={frame} pose={pose} canMove={(to,from)=>clear.canWalk(from,to)}
      keyboard tapToWalk/>:<EyeCamera view={view} scale={scale} frame={frame}/>}
  </>;
}

export default function VariantStudio() {
  const {id}=useParams<{id:string}>();
  const [data,setData]=useState<VariantComparison|null>(null);
  const [mode,setMode]=useState<"compare"|"baseline"|"variant">("compare");
  const [message,setMessage]=useState("");
  const [busy,setBusy]=useState(false);
  useEffect(()=>{
    const controller=new AbortController();
    request<VariantComparison>(`/design-variants/${encodeURIComponent(id)}`,{signal:controller.signal})
      .then(value=>{if(!controller.signal.aborted)setData(value);})
      .catch(error=>{if(!controller.signal.aborted)setMessage(String(error));});
    return ()=>controller.abort();
  },[id]);
  const view=useMemo(()=>data?commonView(data.baseline,data.variant):null,[data]);
  const versions=mode==="compare"?["baseline","variant"] as const:[mode];
  const exportBlocked=!!data?.variant.plan.openings.some(opening=>opening.status==="proposed");
  async function export3D(){
    if(!data)return;
    setBusy(true);setMessage("");
    try{
      const {exportPlan3D}=await import("../../lib/exportPlan3D");
      await exportPlan3D(data.variant.plan,{status:"draft"},data.variant.scene);
    }catch(error){setMessage(String(error));}
    finally{setBusy(false);}
  }
  return <div className="desktop-surface variant-studio">
    <header className="desktop-mast">
      <DesktopBrand/>
      {data&&<Link href={`/plan/${encodeURIComponent(data.sourceId)}?setup=designer`}>Back to Designer</Link>}
    </header>
    <main>
      <h1>{data?.title??"Design comparison"}</h1>
      {message&&<p role="alert">{message}</p>}
      {!data&&!message&&<p role="status">Opening saved plans…</p>}
      {data&&<>
        <p>{Math.round(data.metrics.passage*100)} cm proposed passage · {Math.round(data.metrics.storageDepth*100)} cm storage depth</p>
        {view?<><nav aria-label="Comparison mode">
          <button className="desktop-action" aria-pressed={mode==="compare"} onClick={()=>setMode("compare")}>Compare</button>
          <button className="desktop-action" aria-pressed={mode==="baseline"} onClick={()=>setMode("baseline")}>Walk original</button>
          <button className="desktop-action" aria-pressed={mode==="variant"} onClick={()=>setMode("variant")}>Walk variant</button>
        </nav>
        <div className="variant-viewports" data-walking={mode!=="compare"}>
          {versions.map(version=><section key={version}>
            <h2>{version==="baseline"?"Original":"Variant"}</h2>
            <div className="variant-canvas">
              <Canvas key={mode} shadows frameloop="demand" dpr={[1,1.4]} fallback={<p>Enable WebGL to preview the design.</p>}>
                <ComparisonScene version={data[version]} view={view} walking={mode!=="compare"}/>
              </Canvas>
            </div>
          </section>)}
        </div></>:<p>There’s no shared clear camera position. Open the variant editor to review the layout.</p>}
        <div className="variant-exports">
          <Link className="desktop-action" href={`/plan/${encodeURIComponent(id)}`}>Edit variant</Link>
          {!exportBlocked&&<a className="desktop-action" href={`${API}/blueprints/${encodeURIComponent(id)}/plan/export`}>
            Export plan bundle
          </a>}
          <button className="desktop-action primary" disabled={busy||exportBlocked} onClick={()=>void export3D()}>Export 3D model</button>
          {exportBlocked&&<span>Review proposed openings in the variant before exporting.</span>}
        </div>
      </>}
    </main>
  </div>;
}
