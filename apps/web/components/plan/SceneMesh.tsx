"use client";
import { useEffect, useLayoutEffect, useMemo, useState } from "react";
import { useThree } from "@react-three/fiber";
import * as T from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import type { PlanModel } from "../../lib/plan/model";
import { metersPerPixel, wallFootprint } from "../../lib/plan/derive";
import { doorLeaves } from "../../lib/plan/doorLeaves";
import { wallPieces } from "../../lib/plan/mesh";
import { roomsOf } from "../../lib/plan/walkSpace";
import {yardColor,yardShapes} from "../../lib/plan/yard";
import { roomSurfaces, stairPieces } from "../../lib/plan/stairs";
import {stairCutouts, stairHeadroom} from "../../lib/plan/stairLevels";
import { makeWindows } from "../../lib/plan/windowFrames";
import { savedPose } from "../../lib/plan/camera";
import { floorFinishes, type Capture, type Frame, type Item, type Scene, type View } from "../../lib/plan/scene";
import {homePresets, presetFloor, type HomePreset} from "../../lib/plan/homePresets";
import { furnitureParts, makeFurnitureResources } from "../../lib/plan/furnitureModels";
import { loadFurnitureAsset, scaledFurnitureAsset } from "../../lib/plan/furnitureAssets";
import { floorMaterialFor, floorSurface, floorTexture, loadFloorPhotos, type PhotoFloor } from "../../lib/plan/floorMaterials";
import { wallChunkGeometry, wallSurfaceMaterials } from "../../lib/plan/wallMaterials";
import type { Chunk, WallPiece } from "../../lib/plan/mesh";

export function makeCamera(view: View, scale: number, frame: Frame) {
  const pose = savedPose(view, scale, frame.width/frame.height);
  const camera = new T.PerspectiveCamera(pose.verticalFovDeg, frame.width/frame.height, .03, 80);
  (camera as T.PerspectiveCamera & {manual:boolean}).manual=true;
  camera.position.set(...pose.position);
  camera.lookAt(camera.position.clone().add(new T.Vector3(...pose.direction)));
  camera.updateMatrixWorld();
  return camera;
}

export function EyeCamera({view, scale, frame}: {view: View; scale: number; frame: Frame}) {
  const camera = useMemo(()=>makeCamera(view,scale,frame), [view,scale,frame]);
  const set = useThree(s=>s.set), get = useThree(s=>s.get);
  useLayoutEffect(()=>{
    const previous = get().camera;
    set({camera});
    return ()=>set({camera:previous});
  },[camera,get,set]);
  return null;
}



type FloorStyle = Pick<Scene,"floorFinish"|"floorMaterial"|"roomFloorMaterials">;
type LoadedFloorPhotos = Awaited<ReturnType<typeof loadFloorPhotos>>;

function useFloorPhotos(kind:PhotoFloor, enabled: boolean) {
  const [photos, setPhotos] = useState<LoadedFloorPhotos>(null);
  useEffect(()=>{
    if (!enabled) return;
    let active = true;
    void loadFloorPhotos(kind).then(images=>{if (active) setPhotos(images);});
    return ()=>{active=false;};
  },[kind,enabled]);
  return photos;
}

function useMaterialEnvironment(enabled: boolean) {
  const renderer = useThree(state=>state.gl);
  const [texture, setTexture] = useState<T.Texture | null>(null);
  useEffect(()=>{
    if (!enabled) return;
    const generator = new T.PMREMGenerator(renderer);
    const room = new RoomEnvironment();
    const environment = generator.fromScene(room, .045);
    generator.dispose();
    room.dispose();
    setTexture(environment.texture);
    return ()=>{
      setTexture(null);
      environment.dispose();
    };
  },[renderer,enabled]);
  return texture;
}

function WallChunk({piece,chunk,wallIndex,presentation,finishes,tileMap,wallColor}:{
  piece:WallPiece;chunk:Chunk;wallIndex:number;presentation:boolean;
  finishes:Scene["wallFinishes"];tileMap:T.Texture|null;wallColor?:string;
}){
  const [front,back]=wallSurfaceMaterials(piece,finishes);
  const base=wallColor??(presentation?(piece.material==="concrete"?"#c7c5be":"#efeae0"):(piece.material==="concrete"?"#98a9b6":"#c9d6db"));
  const geometry=useMemo(()=>wallChunkGeometry(piece,chunk),[piece,chunk]);
  useEffect(()=>()=>geometry.dispose(),[geometry]);
  return <mesh geometry={geometry} castShadow={presentation} receiveShadow={presentation}
    userData={{maskId:2000+wallIndex,wallId:piece.id,positiveSide:piece.positiveSide}} position={[(chunk.start+chunk.end-piece.lengthM)/2,(chunk.low+chunk.high)/2,0]}>
    {front||back?[null,null,null,null,front,back].map((material,index)=>
      <meshStandardMaterial key={index} attach={`material-${index}`} color={material?.color??base} map={material?.kind==="tile"?tileMap:null}/>
    ):<meshStandardMaterial color={base}/>}
  </mesh>;
}

type FurnitureAsset = Awaited<ReturnType<typeof loadFurnitureAsset>>;

function CatalogFurniture({asset,item,maskId,presentation,environment}:{asset:NonNullable<FurnitureAsset>;item:Item;
  maskId:number;presentation:boolean;environment:T.Texture|null}){
  const {id,kind,width,height,depth}=item;
  const {model,materials}=useMemo(()=>{
    const model=scaledFurnitureAsset(asset,{kind,width,height,depth});
    const materials=new Map<T.MeshStandardMaterial,T.MeshStandardMaterial>();
    model.traverse(object=>{
      if(!(object instanceof T.Mesh)) return;
      const source=object.material as T.MeshStandardMaterial;
      let material=materials.get(source);
      if(!material){
        material=source.clone();
        material.envMap=environment;
        material.envMapIntensity=.5;
        materials.set(source,material);
      }
      const glass=material.transparent;
      if(glass) material.depthWrite=false;
      object.material=material;
      object.userData={maskId,furnitureId:maskId?id:undefined,pickFixtureId:maskId?undefined:id,glass};
      object.castShadow=presentation&&!glass&&kind!=="rug";
      object.receiveShadow=presentation;
    });
    return {model,materials};
  },[asset,id,kind,width,height,depth,maskId,presentation,environment]);
  useEffect(()=>()=>materials.forEach(material=>material.dispose()),[materials]);
  return <primitive object={model}/>;
}

function FurnitureMeshes({objects,scale,presentation,environment,preview=false,designPreset}:{objects:Item[];scale:number;presentation:boolean;environment:T.Texture|null;preview?:boolean;designPreset?:HomePreset|null}){
  const resources=useMemo(()=>makeFurnitureResources(designPreset),[designPreset]);
  useEffect(()=>()=>resources.dispose(),[resources]);
  const [assets,setAssets]=useState<Partial<Record<Item["kind"],FurnitureAsset>>>({});
  const kinds=[...new Set(objects.map(item=>item.kind))].sort().join(",");
  useEffect(()=>{
    if(!kinds||designPreset) return;
    let active=true;
    for(const kind of kinds.split(",") as Item["kind"][]){
      void loadFurnitureAsset(kind).then(asset=>{
        if(active&&asset) setAssets(current=>current[kind]===asset?current:{...current,[kind]:asset});
      });
    }
    return ()=>{active=false;};
  },[kinds,designPreset]);
  return objects.map((item,index)=>{
    const asset=designPreset?undefined:assets[item.kind];
    return <group key={item.id} position={[item.position.x*scale,0,item.position.y*scale]}
      rotation={[0,-item.rotation*Math.PI/180,0]}>
    {asset?<CatalogFurniture asset={asset} item={item} maskId={preview?0:1000+index} presentation={presentation} environment={environment}/>:
      furnitureParts(item,designPreset).map((part,i)=><mesh key={i} geometry={resources.geometry(part.shape)}
      material={resources.material(part.finish,environment)} dispose={null}
      castShadow={presentation&&part.finish!=="glass"&&item.kind!=="rug"} receiveShadow={presentation}
      position={part.position} scale={part.size} rotation={part.turn??[0,0,0]}
      userData={{maskId:preview?0:1000+index,furnitureId:preview?undefined:item.id,pickFixtureId:preview?item.id:undefined,glass:part.finish==="glass"}}/>)}
    </group>;
  });
}

function Windows({plan,environment,shadows,designPreset,finishes}:{plan:PlanModel;environment:T.Texture|null;shadows:boolean;designPreset?:HomePreset|null;finishes?:Scene["windowFinishes"]}){
  const windows=useMemo(()=>makeWindows(plan,environment,shadows,designPreset?homePresets[designPreset].frame:undefined,finishes),[plan,environment,shadows,designPreset,finishes]);
  useEffect(()=>windows.dispose,[windows]);
  return <primitive object={windows.group}/>;
}

export function SceneMesh({m, objects, detectedObjects = [], closedDoorIds, floorStyle={}, wallFinishes, windowFinishes, designPreset, presentation=false, cutaway=false, walkGround=false, lights=true, showYard=true}: {m: PlanModel; objects: Item[]; detectedObjects?: Item[]; closedDoorIds?: string[]; floorStyle?:FloorStyle; wallFinishes?:Scene["wallFinishes"]; windowFinishes?:Scene["windowFinishes"]; designPreset?:HomePreset|null; presentation?:boolean; cutaway?:boolean; walkGround?:boolean; lights?:boolean; showYard?:boolean}) {
  const scale = metersPerPixel(m)!;
  const {floorFinish="default",floorMaterial,roomFloorMaterials}=floorStyle;
  const preset=designPreset?homePresets[designPreset]:undefined;
  const width=m.imageTransform.width*scale, depth=m.imageTransform.height*scale;
  const sunTarget=useMemo(()=>{const target=new T.Object3D();target.position.set(width/2,0,depth/2);return target;},[width,depth]);
  const shadowSize=Math.max(4,width,depth)*.8;
  const walls = useMemo(()=>wallPieces(m),[m]);
  const tiled=Object.values(wallFinishes??{}).some(({a,b})=>a?.kind==="tile"||b?.kind==="tile");
  const wallTiles=useMemo(()=>tiled?floorTexture({kind:"tile",widthM:.6,lengthM:.6}):null,[tiled]);
  useEffect(()=>()=>wallTiles?.dispose(),[wallTiles]);
  const yards=useMemo(()=>yardShapes(m),[m]);
  const stairs = useMemo(()=>stairPieces(m),[m]);
  useEffect(()=>()=>stairs.forEach(stair=>stair.wells.forEach(well=>well.walls.dispose())),[stairs]);
  const {rooms,ground} = useMemo(()=>{
    const cutouts=stairCutouts(m);
    const rooms=roomsOf(m).map(room=>({room,surfaces:roomSurfaces(room.polygon,scale,cutouts)}));
    const {width,height}=m.imageTransform;
    return {rooms,ground:walkGround?roomSurfaces([{x:0,y:0},{x:width,y:0},{x:width,y:height},{x:0,y:height}],scale,cutouts):[]};
  },[m,scale,walkGround]);
  const ceilings=useMemo(()=>{
    if(cutaway)return [];
    const surfacesAt=(polygon:PlanModel["rooms"][number]["polygon"], height:number)=>
      roomSurfaces(polygon,scale,stairHeadroom(m,height)).map(shape=>({shape,height}));
    const wallHeights=new Map(m.walls.map(wall=>[wall.id,wall.heightM]));
    const roomWalls=new Map(m.rooms.map(room=>[room.id,room.wallIds]));
    if(rooms.length)return rooms.flatMap(({room})=>{
      if(room.roomType==="balcony")return [];
      const boundaryHeights=(roomWalls.get(room.id)??[]).flatMap(id=>{
        const height=wallHeights.get(id);
        return height===undefined?[]:[height];
      });
      const height=room.ceilingHeightM??(boundaryHeights.length?Math.min(...boundaryHeights):2.8);
      return surfacesAt(room.polygon,height);
    });
    // A draft without room polygons can still have an interior roof in Walk.
    const footprint=walkGround&&wallFootprint(m,scale);
    if(!footprint||footprint.width<=0||footprint.depth<=0)return [];
    const {left,right,top,bottom}=footprint;
    return surfacesAt([{x:left,y:top},{x:right,y:top},{x:right,y:bottom},{x:left,y:bottom}],footprint.lowestWall);
  },[m,scale,rooms,cutaway,walkGround]);
  const materials = useMemo(()=>rooms.map(({room})=>
    floorMaterialFor({floorFinish,floorMaterial,roomFloorMaterials},room.id) ??
      presetFloor(designPreset,room.roomType)
  ),[rooms,floorFinish,floorMaterial,roomFloorMaterials,designPreset]);
  const wood = useFloorPhotos("wood", materials.some(material=>material?.kind==="wood"));
  const marble = useFloorPhotos("marble", materials.some(material=>material?.kind==="marble"));
  const tile = useFloorPhotos("tile", materials.some(material=>material?.kind==="tile"));
  const floors = useMemo(()=>{
    const photos = {wood,marble,tile,concrete:null};
    const surfaces = new Map<string,ReturnType<typeof floorSurface>>();
    const finishes = materials.map(material=>{
      if (!material) return floorFinishes[floorFinish];
      const {kind,widthM,lengthM,color}=material;
      const key = JSON.stringify([kind,widthM,lengthM]);
      let surface = surfaces.get(key);
      if (!surface) {
        surface = floorSurface(material, photos[kind]);
        surfaces.set(key,surface);
      }
      return {color,...surface};
    });
    return {surfaces,finishes};
  },[materials,floorFinish,wood,marble,tile]);
  useEffect(()=>()=>floors.surfaces.forEach(({map,normalMap,roughnessMap})=>{
    map.dispose();
    normalMap?.dispose();
    roughnessMap?.dispose();
  }),[floors]);
  const environment = useMaterialEnvironment(presentation &&
    (objects.length>0||detectedObjects.length>0||m.openings.some(o=>o.kind==="window"&&o.status==="confirmed")||
      floors.finishes.some(finish=>"normalMap" in finish && !!finish.normalMap)));
  return <>
    {lights&&(presentation?<><hemisphereLight color="#fff6ea" groundColor="#b4b3aa" intensity={1.45}/>
      <primitive object={sunTarget}/>
      <directionalLight color="#fff0d6" intensity={2} castShadow target={sunTarget}
        position={[width*.25,shadowSize*1.5,-depth*.25]} shadow-mapSize={[1024,1024]}
        shadow-camera-left={-shadowSize} shadow-camera-right={shadowSize} shadow-camera-top={shadowSize}
        shadow-camera-bottom={-shadowSize} shadow-camera-far={shadowSize*4} shadow-normalBias={.022} shadow-bias={-.0001}/>
    </>:<><ambientLight intensity={1.25}/><directionalLight position={[5,10,3]} intensity={2}/></>)}
    {ground.map((shape,index)=><mesh key={"walk-ground-"+index} rotation={[-Math.PI/2,0,0]} position={[0,-.03,0]}
      receiveShadow userData={{furnishGround:true}}>
      <shapeGeometry args={[shape]}/><meshStandardMaterial color="#dad8ce" roughness={.92} side={T.DoubleSide}/>
    </mesh>)}
    {showYard&&yards.map(({shape,surface},i)=><mesh key={"yard"+i} rotation={[-Math.PI/2,0,0]} position={[0,-.01,0]} receiveShadow userData={{maskId:1,furnishGround:true}}>
      <shapeGeometry args={[shape]}/><meshStandardMaterial color={yardColor[surface]} side={T.DoubleSide}/>
    </mesh>)}
    {ceilings.map(({shape,height},index)=><mesh key={index} receiveShadow={presentation}
      rotation={[-Math.PI/2,0,0]} position={[0,height,0]} userData={{maskId:1}}>
      <shapeGeometry args={[shape]}/><meshStandardMaterial color="#f1efea" side={T.BackSide}/>
    </mesh>)}
    {rooms.map(({room,surfaces}, i)=>{
      const finish = floors.finishes[i];
      const photoFloor = "normalMap" in finish && !!finish.normalMap;
      return <group key={room.id}>
        {surfaces.map((shape,j)=><mesh key={j} receiveShadow={presentation} rotation={[-Math.PI/2,0,0]} position={[0,i*0.00002,0]} userData={{maskId:i+2,walkFloor:true}}>
          <shapeGeometry args={[shape]}/>
          <meshStandardMaterial key={photoFloor?"photo":"map" in finish?"pattern":"solid"} {...finish}
            envMap={photoFloor?environment:null} envMapIntensity={.42} side={T.DoubleSide}/>
        </mesh>)}
      </group>;
    })}
    {walls.map((p,wallIndex)=><group key={p.id} position={[p.centre[0],0,p.centre[1]]} rotation={[0,p.angle,0]}>
      {p.chunks.map((chunk,i)=><WallChunk key={i} piece={p} chunk={chunk} wallIndex={wallIndex}
        presentation={presentation} finishes={wallFinishes} tileMap={wallTiles} wallColor={preset?.wall}/>)}
    </group>)}
    <Windows plan={m} environment={environment} shadows={presentation} designPreset={designPreset} finishes={windowFinishes}/>
    {doorLeaves(m,scale,closedDoorIds).map(door=>
      <group key={door.id} position={[door.x,0,door.z]} rotation={[0,door.angle,0]}>
        <mesh userData={{maskId:1,openingId:door.id}} position={[door.length/2,door.height/2,0]}>
          <boxGeometry args={[door.length,door.height,.04]}/><meshStandardMaterial color={preset?.door??"#b9a58d"} roughness={.62}/>
        </mesh>
        <mesh userData={{maskId:1,openingId:door.id}} position={[door.length*.87,door.height*.47,0]}>
          <boxGeometry args={[.095,.023,.092]}/><meshStandardMaterial color={preset?.metal??"#77726a"} metalness={.68} roughness={.3}/>
        </mesh>
      </group>)}
    {stairs.map(stair=><group key={stair.id}>{stair.steps.map((step,i)=><group key={i} rotation={[-Math.PI/2,0,0]} position={[0,step.bottom,0]}>
      <mesh castShadow={presentation} receiveShadow={presentation} userData={{maskId:1}}>
        <extrudeGeometry args={[step.shape,{depth:step.height,bevelEnabled:false}]}/><meshStandardMaterial color="#a39b8d" roughness={.83}/>
      </mesh>
      <mesh position={[0,0,step.height+.001]} receiveShadow={presentation} userData={{maskId:1}}>
        <shapeGeometry args={[step.shape]}/><meshStandardMaterial color="#c6a681" roughness={.68}/>
      </mesh>
    </group>)}
      {stair.wells.map((well,i)=><group key={i}>
        <mesh geometry={well.walls} receiveShadow={presentation} userData={{maskId:1}}>
          <meshStandardMaterial color="#aeaba0" side={T.DoubleSide}/>
        </mesh>
        <mesh rotation={[-Math.PI/2,0,0]} position={[0,well.bottom,0]} receiveShadow={presentation} userData={{maskId:1}}>
          <shapeGeometry args={[well.shape]}/><meshStandardMaterial color="#958d80"/>
        </mesh>
      </group>)}
    </group>)}
    <FurnitureMeshes designPreset={designPreset} objects={objects} scale={scale} presentation={presentation} environment={environment}/>
    {detectedObjects.length>0&&<group name="Detected furniture preview" userData={{fixturePreview:true}}>
      <FurnitureMeshes preview designPreset={designPreset} objects={detectedObjects} scale={scale} presentation={presentation} environment={environment}/>
    </group>}
  </>;
}

const vertex = `varying float depth; void main(){vec4 p=modelViewMatrix*vec4(position,1.0);depth=-p.z;gl_Position=projectionMatrix*p;}`;
const pack = `vec3 packId(float n){return vec3(floor(n/65536.0),mod(floor(n/256.0),256.0),mod(n,256.0))/255.0;}`;

export function CaptureBridge({bind}: {bind: (fn: ((view: View, scale: number, frame: Frame, fingerprint: string)=>Capture) | null)=>void}) {
  const {gl,scene} = useThree();
  useLayoutEffect(()=>{
    bind((view,scale,frame,fingerprint)=>{
      const camera=makeCamera(view,scale,frame), {width,height}=frame;
      const target=new T.WebGLRenderTarget(width,height);
      const prior=gl.getRenderTarget(), bg=scene.background;
      const oldViewport=gl.getViewport(new T.Vector4()), oldScissor=gl.getScissor(new T.Vector4()), oldTest=gl.getScissorTest();
      const meshes:T.Mesh[]=[], hidden:T.Object3D[]=[];
      const original=new Map<T.Mesh,T.Material|T.Material[]>();
      const masks=new Map<number,T.ShaderMaterial>();
      const depth=new T.ShaderMaterial({vertexShader:vertex, fragmentShader:
        `varying float depth; ${pack} void main(){gl_FragColor=vec4(packId(max(1.0,floor(depth*1000.0+0.5))),1.0);}`,
        side:T.DoubleSide});
      const coverage:Record<number,number>={};
      const visibleRegions:Capture["visibleRegions"]={};
      let depthPixels:Uint8Array;
      function pass(kind:"preview"|"depth"|"mask") {
        gl.clear();
        gl.render(scene,camera);
        const rgba=new Uint8Array(width*height*4);
        gl.readRenderTargetPixels(target,0,0,width,height,rgba);
        const canvas=document.createElement("canvas");
        canvas.width=width; canvas.height=height;
        const ctx=canvas.getContext("2d")!;
        const img=ctx.createImageData(width,height);
        for(let y=0;y<height;y++) img.data.set(rgba.subarray(y*width*4,(y+1)*width*4),(height-y-1)*width*4);
        if(kind==="depth")depthPixels=rgba;
        if(kind==="mask") for(let i=0;i<rgba.length;i+=4){
          const id=rgba[i]*65536+rgba[i+1]*256+rgba[i+2];
          coverage[id]=(coverage[id]||0)+1;
          if(!id)continue;
          const pixel=i/4, x=pixel%width, y=height-1-Math.floor(pixel/width);
          const mm=depthPixels[i]*65536+depthPixels[i+1]*256+depthPixels[i+2];
          const region=visibleRegions[id]??={pixels:0,boundsXY:[x,y,x,y],depthMm:[mm,mm]};
          const box=region.boundsXY;
          box[0]=Math.min(box[0],x); box[1]=Math.min(box[1],y);
          box[2]=Math.max(box[2],x); box[3]=Math.max(box[3],y);
          region.depthMm[0]=Math.min(region.depthMm[0],mm);
          region.depthMm[1]=Math.max(region.depthMm[1],mm);
          region.pixels++;
        }
        ctx.putImageData(img,0,0);
        return canvas.toDataURL("image/png");
      }
      try {
        scene.traverse(o=>{
          if(o.userData.fixturePreview&&o.visible){o.visible=false;hidden.push(o);}
          if(!(o instanceof T.Mesh)) return;
          if(o.userData.maskId) meshes.push(o);
          else if(o.visible){o.visible=false;hidden.push(o);}
        });
        scene.background=new T.Color("#e9eff2");
        gl.setRenderTarget(target);
        gl.setScissorTest(false);
        target.texture.colorSpace=T.SRGBColorSpace;
        const preview=pass("preview");
        target.texture.colorSpace=T.NoColorSpace;
        scene.background=new T.Color(0);
        for(const m of meshes){
          if(m.userData.glass && m.visible){m.visible=false;hidden.push(m);}
          original.set(m,m.material);
          m.material=depth;
        }
        const depthPNG=pass("depth");
        for(const m of meshes){
          const id=m.userData.maskId as number;
          if(!masks.has(id)) masks.set(id,new T.ShaderMaterial({vertexShader:vertex,
            fragmentShader:`${pack} void main(){gl_FragColor=vec4(packId(${id}.0),1.0);}`, side:T.DoubleSide}));
          m.material=masks.get(id)!;
        }
        const mask=pass("mask");
        return {preview,depth:depthPNG,mask,coverage,visibleRegions,fingerprint};
      } finally {
        original.forEach((v,k)=>k.material=v);
        hidden.forEach(o=>o.visible=true);
        scene.background=bg;
        gl.setRenderTarget(prior);
        gl.setViewport(oldViewport);
        gl.setScissor(oldScissor);
        gl.setScissorTest(oldTest);
        target.dispose();depth.dispose();masks.forEach(m=>m.dispose());
      }
    });
    return ()=>bind(null);
  },[bind,gl,scene]);
  return null;
}
