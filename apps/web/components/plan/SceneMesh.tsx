"use client";
import { useEffect, useLayoutEffect, useMemo, useState } from "react";
import { useThree } from "@react-three/fiber";
import * as T from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import type { PlanModel } from "../../lib/plan/model";
import { metersPerPixel, openingEnds } from "../../lib/plan/derive";
import { wallPieces } from "../../lib/plan/mesh";
import { roomsOf } from "../../lib/plan/walkSpace";
import {yardShapes} from "../../lib/plan/yard";
import { stairPieces } from "../../lib/plan/stairs";
import { savedPose } from "../../lib/plan/camera";
import { floorFinishes, type Capture, type Frame, type Item, type Scene, type View } from "../../lib/plan/scene";
import { furnitureParts, makeFurnitureResources } from "../../lib/plan/furnitureModels";
import { floorMaterialFor, floorSurface, floorTexture, loadFloorPhotos } from "../../lib/plan/floorMaterials";
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

function useFloorPhotos(kind: "wood" | "marble", enabled: boolean) {
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

function WallChunk({piece,chunk,wallIndex,presentation,finishes,tileMap}:{
  piece:WallPiece;chunk:Chunk;wallIndex:number;presentation:boolean;
  finishes:Scene["wallFinishes"];tileMap:T.Texture|null;
}){
  const [front,back]=wallSurfaceMaterials(piece,finishes);
  const base=presentation?(piece.material==="concrete"?"#c7c5be":"#efeae0"):(piece.material==="concrete"?"#98a9b6":"#c9d6db");
  const geometry=useMemo(()=>wallChunkGeometry(piece,chunk),[piece,chunk]);
  useEffect(()=>()=>geometry.dispose(),[geometry]);
  return <mesh geometry={geometry} castShadow={presentation} receiveShadow={presentation}
    userData={{maskId:2000+wallIndex}} position={[(chunk.start+chunk.end-piece.lengthM)/2,(chunk.low+chunk.high)/2,0]}>
    {front||back?[null,null,null,null,front,back].map((material,index)=>
      <meshStandardMaterial key={index} attach={`material-${index}`} color={material?.color??base} map={material?.kind==="tile"?tileMap:null}/>
    ):<meshStandardMaterial color={base}/>}
  </mesh>;
}

function FurnitureMeshes({objects,scale,presentation,environment}:{objects:Item[];scale:number;presentation:boolean;environment:T.Texture|null}){
  const resources=useMemo(()=>makeFurnitureResources(),[]);
  useEffect(()=>()=>resources.dispose(),[resources]);
  return objects.map((item,index)=><group key={item.id} position={[item.position.x*scale,0,item.position.y*scale]}
    rotation={[0,-item.rotation*Math.PI/180,0]}>
    {furnitureParts(item).map((part,i)=><mesh key={i} geometry={resources.geometry(part.shape)}
      material={resources.material(part.finish,environment)} dispose={null}
      castShadow={presentation&&part.finish!=="glass"&&item.kind!=="rug"} receiveShadow={presentation}
      position={part.position} scale={part.size} rotation={part.turn??[0,0,0]}
      userData={{maskId:1000+index,furnitureId:item.id,glass:part.finish==="glass"}}/>)}
  </group>);
}

export function SceneMesh({m, objects, closedDoorIds, floorStyle={}, wallFinishes, presentation=false, cutaway=false}: {m: PlanModel; objects: Item[]; closedDoorIds?: string[]; floorStyle?:FloorStyle; wallFinishes?:Scene["wallFinishes"]; presentation?:boolean; cutaway?:boolean}) {
  const scale = metersPerPixel(m)!;
  const {floorFinish="default",floorMaterial,roomFloorMaterials}=floorStyle;
  const width=m.imageTransform.width*scale, depth=m.imageTransform.height*scale;
  const sunTarget=useMemo(()=>{const target=new T.Object3D();target.position.set(width/2,0,depth/2);return target;},[width,depth]);
  const shadowSize=Math.max(4,width,depth)*.8;
  const walls = useMemo(()=>wallPieces(m),[m]);
  const tiled=Object.values(wallFinishes??{}).some(({a,b})=>a?.kind==="tile"||b?.kind==="tile");
  const wallTiles=useMemo(()=>tiled?floorTexture({kind:"tile",widthM:.6,lengthM:.6}):null,[tiled]);
  useEffect(()=>()=>wallTiles?.dispose(),[wallTiles]);
  const yards=useMemo(()=>yardShapes(m),[m]);
  const stairs = useMemo(()=>stairPieces(m),[m]);
  const rooms = useMemo(()=>roomsOf(m).map(r=>{
    const shape = new T.Shape(r.polygon.map(p=>new T.Vector2(p.x*scale,-p.y*scale)));
    return {room:r, shape};
  }),[m,scale]);
  const materials = useMemo(()=>rooms.map(({room})=>
    floorMaterialFor({floorFinish,floorMaterial,roomFloorMaterials},room.id)
  ),[rooms,floorFinish,floorMaterial,roomFloorMaterials]);
  const wood = useFloorPhotos("wood", materials.some(material=>material?.kind==="wood"));
  const marble = useFloorPhotos("marble", materials.some(material=>material?.kind==="marble"));
  const floors = useMemo(()=>{
    const surfaces = new Map<string,ReturnType<typeof floorSurface>>();
    const finishes = materials.map(material=>{
      if (!material) return floorFinishes[floorFinish];
      const {kind,widthM,lengthM,color}=material;
      const key = JSON.stringify([kind,widthM,lengthM]);
      let surface = surfaces.get(key);
      if (!surface) {
        const photos = kind==="wood" ? wood : kind==="marble" ? marble : null;
        surface = floorSurface(material, photos);
        surfaces.set(key,surface);
      }
      return {color,...surface};
    });
    return {surfaces,finishes};
  },[materials,floorFinish,wood,marble]);
  useEffect(()=>()=>floors.surfaces.forEach(({map,normalMap,roughnessMap})=>{
    map.dispose();
    normalMap?.dispose();
    roughnessMap?.dispose();
  }),[floors]);
  const environment = useMaterialEnvironment(presentation &&
    (objects.length>0||floors.finishes.some(finish=>"normalMap" in finish && !!finish.normalMap)));
  return <>
    {presentation?<><hemisphereLight color="#fff3df" groundColor="#9b9b8f" intensity={1.45}/>
      <primitive object={sunTarget}/>
      <directionalLight color="#fff0d6" intensity={2} castShadow target={sunTarget}
        position={[width*.25,shadowSize*1.5,-depth*.25]} shadow-mapSize={[1024,1024]}
        shadow-camera-left={-shadowSize} shadow-camera-right={shadowSize} shadow-camera-top={shadowSize}
        shadow-camera-bottom={-shadowSize} shadow-camera-far={shadowSize*4} shadow-normalBias={.035}/>
    </>:<><ambientLight intensity={1.25}/><directionalLight position={[5,10,3]} intensity={2}/></>}
    {yards.map((shape,i)=><mesh key={"yard"+i} rotation={[-Math.PI/2,0,0]} position={[0,-.01,0]} receiveShadow userData={{maskId:1,furnishGround:true}}>
      <shapeGeometry args={[shape]}/><meshStandardMaterial color="#839768" side={T.DoubleSide}/>
    </mesh>)}
    {rooms.map(({room,shape}, i)=>{
      const finish = floors.finishes[i];
      const photoFloor = "normalMap" in finish && !!finish.normalMap;
      return <group key={room.id}>
        <mesh receiveShadow={presentation} rotation={[-Math.PI/2,0,0]} position={[0,i*0.00002,0]} userData={{maskId:i+2,walkFloor:true}}>
          <shapeGeometry args={[shape]}/>
          <meshStandardMaterial key={photoFloor?"photo":"map" in finish?"pattern":"solid"} {...finish}
            envMap={photoFloor?environment:null} envMapIntensity={.42} side={T.DoubleSide}/>
        </mesh>
        {!cutaway&&room.roomType!=="balcony"&&<mesh receiveShadow={presentation} rotation={[-Math.PI/2,0,0]} position={[0,room.ceilingHeightM ?? 2.8,0]} userData={{maskId:1}}>
          <shapeGeometry args={[shape]}/><meshStandardMaterial color="#f1efea" side={T.BackSide}/>
        </mesh>}
      </group>;
    })}
    {walls.map((p,wallIndex)=><group key={p.id} position={[p.centre[0],0,p.centre[1]]} rotation={[0,p.angle,0]}>
      {p.chunks.map((chunk,i)=><WallChunk key={i} piece={p} chunk={chunk} wallIndex={wallIndex}
        presentation={presentation} finishes={wallFinishes} tileMap={wallTiles}/>)}
    </group>)}
    {m.openings.filter(o=>o.status==="confirmed"&&(o.kind==="door"||o.kind==="window")).map(o=>{
      const endpoints=openingEnds(m,o);
      if(!endpoints) return null;
      const [a,b]=endpoints, length=Math.hypot(b.x-a.x,b.y-a.y)*scale;
      const angle=Math.atan2(b.y-a.y,b.x-a.x);
      if(o.kind==="window") return <mesh key={o.id} userData={{maskId:1,glass:true}}
        position={[(a.x+b.x)*scale/2,o.sillM+o.heightM/2,(a.y+b.y)*scale/2]} rotation={[0,-angle,0]}>
        <boxGeometry args={[length,o.heightM,.018]}/><meshStandardMaterial transparent opacity={.21} color="#aacbd5" depthWrite={false}/>
      </mesh>;
      // The cut remains open; draw a leaf swung 90 degrees when swing evidence exists.
      const closed=closedDoorIds?.includes(o.id);
      if(!o.swing&&!closed) return null;
      const end=o.hinge==="end", hinge=end?b:a;
      const swung=closed?angle+(end?Math.PI:0):angle+(o.swing==="left"?1:-1)*Math.PI/2;
      return <group key={o.id} position={[hinge.x*scale,0,hinge.y*scale]} rotation={[0,-swung,0]}>
        <mesh userData={{maskId:1}} position={[length/2,o.heightM/2,0]}>
          <boxGeometry args={[length,o.heightM,.04]}/><meshStandardMaterial color="#b9a58d"/>
        </mesh>
      </group>;
    })}
    {stairs.map(stair=><group key={stair.id}>{stair.steps.map((step,i)=><mesh key={i} rotation={[-Math.PI/2,0,0]} userData={{maskId:1}}>
      <extrudeGeometry args={[step.shape,{depth:step.height,bevelEnabled:false}]}/><meshStandardMaterial color="#a9b9b2"/>
    </mesh>)}</group>)}
    <FurnitureMeshes objects={objects} scale={scale} presentation={presentation} environment={environment}/>
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
