"use client";
import { useLayoutEffect, useMemo } from "react";
import { useThree } from "@react-three/fiber";
import * as T from "three";
import type { PlanModel } from "../../lib/plan/model";
import { metersPerPixel, openingEnds } from "../../lib/plan/derive";
import { wallPieces } from "../../lib/plan/mesh";
import { stairPieces } from "../../lib/plan/stairs";
import { savedPose } from "../../lib/plan/camera";
import { blocks, type Capture, type Frame, type Item, type View } from "../../lib/plan/scene";

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

export const roomsOf = (m: PlanModel) => [...m.rooms, ...(m.roomZones || [])].slice(0, 990);

export function SceneMesh({m, objects, closedDoorIds}: {m: PlanModel; objects: Item[]; closedDoorIds?: string[]}) {
  const scale = metersPerPixel(m)!;
  const walls = useMemo(()=>wallPieces(m),[m]);
  const stairs = useMemo(()=>stairPieces(m),[m]);
  const rooms = useMemo(()=>roomsOf(m).map(r=>{
    const shape = new T.Shape(r.polygon.map(p=>new T.Vector2(p.x*scale,-p.y*scale)));
    return {room:r, shape};
  }),[m,scale]);
  return <>
    <ambientLight intensity={1.25}/>
    <directionalLight position={[5,10,3]} intensity={2}/>
    {rooms.map(({room,shape}, i)=><group key={room.id}>
      <mesh rotation={[-Math.PI/2,0,0]} position={[0,i*0.00002,0]} userData={{maskId:i+2}}>
        <shapeGeometry args={[shape]}/><meshStandardMaterial color="#dbe2d8" side={T.DoubleSide}/>
      </mesh>
      <mesh rotation={[-Math.PI/2,0,0]} position={[0,room.ceilingHeightM ?? 2.8,0]} userData={{maskId:1}}>
        <shapeGeometry args={[shape]}/><meshStandardMaterial color="#f1efea" side={T.BackSide}/>
      </mesh>
    </group>)}
    {walls.map((p,wallIndex)=><group key={p.id} position={[p.centre[0],0,p.centre[1]]} rotation={[0,p.angle,0]}>
      {p.chunks.map((c,i)=><mesh key={i} userData={{maskId:2000+wallIndex}} position={[(c.start+c.end-p.lengthM)/2,(c.low+c.high)/2,0]}>
        <boxGeometry args={[c.end-c.start,c.high-c.low,p.thicknessM]}/>
        <meshStandardMaterial color={p.material==="concrete"?"#98a9b6":"#c9d6db"}/>
      </mesh>)}
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
    {objects.map((o,i)=><group key={o.id} position={[o.position.x*scale,0,o.position.y*scale]} rotation={[0,-o.rotation*Math.PI/180,0]}>
      {blocks(o).map((b,j)=><mesh key={j} position={b.position} userData={{maskId:1000+i}}>
        <boxGeometry args={b.size}/><meshStandardMaterial color={b.color}/>
      </mesh>)}
    </group>)}
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
      function pass(mask=false) {
        gl.clear();
        gl.render(scene,camera);
        const rgba=new Uint8Array(width*height*4);
        gl.readRenderTargetPixels(target,0,0,width,height,rgba);
        const canvas=document.createElement("canvas");
        canvas.width=width; canvas.height=height;
        const ctx=canvas.getContext("2d")!;
        const img=ctx.createImageData(width,height);
        for(let y=0;y<height;y++) img.data.set(rgba.subarray(y*width*4,(y+1)*width*4),(height-y-1)*width*4);
        if(mask) for(let i=0;i<rgba.length;i+=4){
          const id=rgba[i]*65536+rgba[i+1]*256+rgba[i+2];
          coverage[id]=(coverage[id]||0)+1;
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
        const preview=pass();
        target.texture.colorSpace=T.NoColorSpace;
        scene.background=new T.Color(0);
        for(const m of meshes){
          if(m.userData.glass && m.visible){m.visible=false;hidden.push(m);}
          original.set(m,m.material);
          m.material=depth;
        }
        const depthPNG=pass();
        for(const m of meshes){
          const id=m.userData.maskId as number;
          if(!masks.has(id)) masks.set(id,new T.ShaderMaterial({vertexShader:vertex,
            fragmentShader:`${pack} void main(){gl_FragColor=vec4(packId(${id}.0),1.0);}`, side:T.DoubleSide}));
          m.material=masks.get(id)!;
        }
        const mask=pass(true);
        return {preview,depth:depthPNG,mask,coverage,fingerprint};
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
