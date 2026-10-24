'use client';
import {useMemo} from 'react';
import {Canvas} from '@react-three/fiber';
import {OrbitControls, Grid} from '@react-three/drei';
import * as THREE from 'three';
import type {Geometry, Pt, Wall} from '../lib/api';

// The editable 2D room outlines are authoritative for the displayed 3D shell.
// Legacy w0-w3 starter walls are deliberately not rendered as a second rectangle.
type Edge = {a:Pt;b:Pt;id:string;thickness:number;height:number};
function validPolygon(points:Pt[]):boolean {
  if(points.length<3)return false;
  const cross=(a:Pt,b:Pt,c:Pt)=>(b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x);
  let area=0;
  for(let i=0;i<points.length;i++){const a=points[i],b=points[(i+1)%points.length];area+=a.x*b.y-b.x*a.y;}
  if(Math.abs(area)<8)return false;
  for(let i=0;i<points.length;i++)for(let j=i+1;j<points.length;j++){
    if(j===i+1 || (i===0&&j===points.length-1))continue;
    const a=points[i],b=points[(i+1)%points.length],c=points[j],d=points[(j+1)%points.length];
    const c1=cross(a,b,c),c2=cross(a,b,d),c3=cross(c,d,a),c4=cross(c,d,b);
    if(c1*c2<0&&c3*c4<0)return false;
  }
  return true;
}
const key=(p:Pt)=>[Math.round(p.x*10)/10,Math.round(p.y*10)/10].join(',');
function shellEdges(geometry:Geometry):Edge[]{
  const unique=new Map<string,Edge>();
  for(const r of geometry.rooms){
    if(!validPolygon(r.points))continue;
    r.points.forEach((a,i)=>{
      const b=r.points[(i+1)%r.points.length];
      if(Math.hypot(a.x-b.x,a.y-b.y)<2)return;
      const ends=[key(a),key(b)].sort().join('|');
      if(!unique.has(ends))unique.set(ends,{a,b,id:'boundary-'+ends,thickness:.15,height:2.8});
    });
  }
  return [...unique.values()];
}
function WallMesh({edge,scale,color}:{edge:Edge;scale:number;color:string}){
  const dx=edge.b.x-edge.a.x,dz=edge.b.y-edge.a.y;
  const len=Math.hypot(dx,dz)/scale;
  return <mesh position={[(edge.a.x+edge.b.x)/(2*scale),edge.height/2,(edge.a.y+edge.b.y)/(2*scale)]}
    rotation={[0,-Math.atan2(dz,dx),0]}>
    <boxGeometry args={[len,edge.height,edge.thickness]}/>
    <meshStandardMaterial color={color} transparent opacity={.76}/>
  </mesh>;
}
export default function Viewer3D({geometry}:{geometry:Geometry}){
  const scale=geometry.px_per_meter||60;
  const data=useMemo(()=>{
    const edges=shellEdges(geometry);
    const floors=geometry.rooms.filter(r=>validPolygon(r.points)).map(r=>{
      const shape=new THREE.Shape();
      // Shape's Y maps to positive world Z after the -90deg X rotation.
      r.points.forEach((p,i)=>{const x=p.x/scale,y=-p.y/scale;if(i===0)shape.moveTo(x,y);else shape.lineTo(x,y);});
      shape.closePath();const g=new THREE.ShapeGeometry(shape);g.rotateX(-Math.PI/2);
      return {id:r.id,mesh:g};
    });
    // AI/proposed and manually placed walls not already represented as room boundary.
    // Avoid double-rendering legacy starter rectangle and coincident edges.
    const independent=geometry.walls.filter(w=>{
      if(/^w[0-3]$/.test(w.id)&&geometry.rooms.length===1)return false;
      const m={x:(w.start.x+w.end.x)/2,y:(w.start.y+w.end.y)/2};
      return !edges.some(e=>{
        const d=Math.hypot(e.b.x-e.a.x,e.b.y-e.a.y);
        if(d<1)return false;
        const t=Math.max(0,Math.min(1,((m.x-e.a.x)*(e.b.x-e.a.x)+(m.y-e.a.y)*(e.b.y-e.a.y))/(d*d)));
        return Math.hypot(m.x-(e.a.x+t*(e.b.x-e.a.x)),m.y-(e.a.y+t*(e.b.y-e.a.y)))<3;
      });
    });
    return {edges,floors,independent};
  },[geometry,scale]);
  const target:[number,number,number]=[geometry.width_px/(2*scale),0,geometry.height_px/(2*scale)];
  return <div style={{height:440,width:'100%',background:'#f0f3f7',borderRadius:12}}>
    <Canvas camera={{position:[target[0]+6,7,target[2]+8],fov:60}}>
      <ambientLight intensity={1.8}/><directionalLight position={[5,10,3]} intensity={2}/>
      <Grid infiniteGrid cellSize={1} sectionSize={5}/>
      {data.floors.map(f=><mesh key={f.id} geometry={f.mesh} position={[0,.015,0]}>
        <meshStandardMaterial color="#dceae2" side={THREE.DoubleSide}/></mesh>)}
      {data.edges.map(e=><WallMesh key={e.id} edge={e} scale={scale} color="#d1dae0"/>)}
      {data.independent.map(w=><WallMesh key={w.id} edge={{a:w.start,b:w.end,id:w.id,thickness:w.thickness_m,height:w.height_m}} scale={scale} color="#5b8aab"/>)}
      <OrbitControls makeDefault target={target}/>
    </Canvas>
    {geometry.rooms.some(r=>!validPolygon(r.points))&&<p className="notice">A room polygon is invalid or self-intersecting; its 3D floor and boundary were skipped. Correct it in 2D.</p>}
  </div>;
}
