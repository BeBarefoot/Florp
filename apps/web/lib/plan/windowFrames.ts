import {BoxGeometry, DoubleSide, Group, Mesh, MeshPhysicalMaterial, MeshStandardMaterial, PlaneGeometry, type Texture} from "three";
import {metersPerPixel, openingEnds} from "./derive";
import type {PlanModel} from "./model";
import {windowFrameFor} from "./windowStyle";

export function makeWindows(model: PlanModel, environment: Texture|null = null, shadows = false) {
  const scale=metersPerPixel(model);
  const group=new Group();
  const resources=new Set<{dispose:()=>void}>();
  if(scale) for(const opening of model.openings){
    if(opening.kind!=="window"||opening.status!=="confirmed")continue;
    const ends=openingEnds(model,opening);
    if(!ends)continue;
    const [a,b]=ends;
    const width=Math.hypot(b.x-a.x,b.y-a.y)*scale;
    const height=opening.heightM;
    if(width<=0||height<=0)continue;
    const frame=windowFrameFor(opening);
    const rail=Math.min(frame.widthM,width*.21,height*.21);
    const wall=model.walls.find(w=>w.id===opening.hostWallId);
    const reveal=Math.max(.025,(wall?.thicknessPx??0)*scale);
    const frameDepth=Math.min(.095,reveal*.86);
    const unit=new Group();
    unit.name="Window "+opening.id;
    unit.userData={kind:"window",id:opening.id,frame,widthM:width,heightM:height,sillM:opening.sillM};
    unit.position.set((a.x+b.x)*scale/2,opening.sillM+height/2,(a.y+b.y)*scale/2);
    unit.rotation.y=-Math.atan2(b.y-a.y,b.x-a.x);
    group.add(unit);

    const aluminium=frame.material==="aluminium";
    const trim=new MeshStandardMaterial({color:frame.color,roughness:aluminium?.34:frame.material==="wood"?.62:.48,
      metalness:aluminium?.42:0,envMap:environment,envMapIntensity:.55});
    const seal=new MeshStandardMaterial({color:"#4c5654",roughness:.84});
    const glazing=new MeshPhysicalMaterial({color:"#c5e1e6",roughness:.15,clearcoat:1,clearcoatRoughness:.09,
      transparent:true,opacity:.20,side:DoubleSide,depthWrite:false,envMap:environment,envMapIntensity:.62});
    resources.add(trim).add(seal).add(glazing);
    function mesh(geometry:BoxGeometry|PlaneGeometry,material:MeshStandardMaterial,x:number,y:number,z:number,isGlass=false){
      resources.add(geometry);
      const part=new Mesh(geometry,material);
      part.position.set(x,y,z);
      part.castShadow=shadows&&!isGlass;
      part.receiveShadow=shadows&&!isGlass;
      part.userData={maskId:1,glass:isGlass};
      unit.add(part);
    }
    for(const side of [-1,1]){
      mesh(new BoxGeometry(rail,height,frameDepth),trim,side*(width-rail)/2,0,0);
      mesh(new BoxGeometry(width-2*rail,rail,frameDepth),trim,0,side*(height-rail)/2,0);
    }
    // The inner lining and the deeper sill give the opening a visible reveal from either side.
    mesh(new BoxGeometry(width,reveal*.055,reveal),trim,0,-height/2+reveal*.0275,0);
    if(frame.panes===2)mesh(new BoxGeometry(rail,height-2*rail,frameDepth),trim,0,0,0);
    const paneWidth=(width-(frame.panes+1)*rail)/frame.panes;
    const paneHeight=height-2*rail;
    const gasket=Math.min(.009,rail*.18,paneWidth*.08,paneHeight*.08);
    for(let i=0;i<frame.panes;i++){
      const x=(i-(frame.panes-1)/2)*(paneWidth+rail);
      for(const side of [-1,1]){
        mesh(new BoxGeometry(gasket,paneHeight,.022),seal,x+side*paneWidth/2,0,0);
        mesh(new BoxGeometry(paneWidth,gasket,.022),seal,x,side*paneHeight/2,0);
      }
      mesh(new PlaneGeometry(paneWidth,paneHeight),glazing,x,0,0,true);
    }
  }
  return {group,dispose:()=>resources.forEach(resource=>resource.dispose())};
}
