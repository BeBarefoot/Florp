"use client";
import {useLayoutEffect} from "react";
import {RoundedBox,useTexture} from "@react-three/drei";
import {DoubleSide,RepeatWrapping,SRGBColorSpace,Vector2} from "three";
import {blocks,type FloorFinish,type Item} from "../../lib/plan/scene";

const surfaces = {
  default: {asset:"smooth_concrete_floor", metres:2, tint:"#f7f3eb"},
  oak: {asset:"rectangular_parquet", metres:2.25, tint:"#ffffff"},
  slate: {asset:"slate_floor", metres:2.29, tint:"#bfc8cf"},
  limestone: {asset:"smooth_concrete_floor", metres:2, tint:"#f4dfc2"},
};

export function TourFloorMaterial({finish}:{finish:FloorFinish}){
  const {asset,metres,tint}=surfaces[finish];
  const path="/materials/"+asset+"-";
  const [map,normalMap,roughnessMap]=useTexture([path+"color.webp",path+"normal.webp",path+"roughness.webp"]);
  useLayoutEffect(()=>{
    map.colorSpace=SRGBColorSpace;
    for(const texture of [map,normalMap,roughnessMap]){
      texture.wrapS=texture.wrapT=RepeatWrapping;
      texture.repeat.setScalar(1/metres);
      texture.anisotropy=4;
      texture.needsUpdate=true;
    }
  },[map,normalMap,roughnessMap,metres]);
  return <meshStandardMaterial color={tint} map={map} normalMap={normalMap} roughnessMap={roughnessMap}
    roughness={1} side={DoubleSide}/>;
}

// Cross-section runs from the pedestal up over the rim and down inside the bowl.
const bowlProfile=[[.19,0],[.24,.025],[.23,.2],[.29,.28],[.46,.42],[.49,.51],
  [.48,.54],[.40,.55],[.37,.52],[.31,.42],[.20,.35],[.08,.31],[0,.31]].map(([r,y])=>new Vector2(r,y));

export function TourFixture({item,maskId}:{item:Item;maskId:number}){
  const {width:w,height:h,depth:d}=item;
  const tags={maskId};
  if(item.kind==="toilet")return <>
    <mesh position={[0,0,.12*d]} scale={[w,h,.75*d]} castShadow receiveShadow userData={tags}>
      <latheGeometry args={[bowlProfile,40]}/><meshStandardMaterial color="#f5f4ee" roughness={.18}/>
    </mesh>
    <RoundedBox args={[w,.53*h,.28*d]} position={[0,.735*h,-.36*d]} radius={Math.min(w,h,d)*.07}
      smoothness={2} castShadow receiveShadow userData={tags}>
      <meshStandardMaterial color="#f4f3ea" roughness={.2}/>
    </RoundedBox>
    <mesh position={[0,.998*h,-.36*d]} scale={[w*.10,h*.002,d*.047]} userData={tags}>
      <sphereGeometry args={[1,16,8]}/><meshStandardMaterial color="#adb2ae" metalness={.52} roughness={.25}/>
    </mesh>
  </>;
  return <>{blocks(item).map((part,i)=>{
    const soft=item.kind==="bed"&&i>=2;
    const glass=item.kind==="shower"&&i>0;
    return <RoundedBox key={i} args={part.size} position={part.position} radius={Math.min(...part.size)*(soft?.42:.08)}
      smoothness={2} castShadow={!glass} receiveShadow userData={tags}>
      <meshStandardMaterial color={part.color} roughness={soft?.95:glass?.12:.58}
        transparent={glass} opacity={glass?.22:1} depthWrite={!glass}/>
    </RoundedBox>;
  })}
  {item.kind==="bed"&&<RoundedBox args={[item.mattressWidth??w,.08*h,(item.mattressDepth??d*.95)*.62]}
    position={[0,.63*h,.18*d]} radius={.035*h} smoothness={2} castShadow receiveShadow userData={tags}>
    <meshStandardMaterial color="#86917d" roughness={.94}/>
  </RoundedBox>}
  </>;
}
