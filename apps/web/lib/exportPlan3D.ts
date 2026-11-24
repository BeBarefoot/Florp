import * as THREE from "three";
import { GLTFExporter } from "three/examples/jsm/exporters/GLTFExporter.js";
import type { PlanModel } from "./plan/model";
import { metersPerPixel } from "./plan/derive";
import { floorOutlines, wallPieces } from "./plan/mesh";
import {yardShapes} from "./plan/yard";
import { stairPieces } from "./plan/stairs";
import { floorMaterialFor, floorSurface, floorTexture, loadFloorPhotos } from "./plan/floorMaterials";
import { floorFinishes, type Scene } from "./plan/scene";
import { wallChunkGeometry, wallSurfaceMaterials } from "./plan/wallMaterials";

/** Metric glTF (meters) with stable wall/room/opening IDs in node extras. */
export async function exportPlan3D(m: PlanModel, review: unknown = {status:"draft"}, config?: Scene) {
  const scale = metersPerPixel(m);
  if (!scale) throw Error("Set one measurement first");
  if (m.openings.some((o) => o.status === "proposed"))
    throw Error("Approve or reject every proposed door and window before exporting 3D.");
  const scene = new THREE.Scene();
  const textures: THREE.Texture[] = [];
  let wallTile: THREE.Texture|null=null;
  scene.userData = {planRevision:m.revision, architectureReview:review};
  for (const piece of wallPieces(m)) {
    const group = new THREE.Group();
    group.name = piece.id;
    group.userData = {
      kind: "wall",
      id: piece.id,
      material: piece.material,
      openings: m.openings
        .filter((o) => o.hostWallId === piece.id && o.status === "confirmed")
        .map((o) => ({ id: o.id, kind: o.kind })),
    };
    group.position.set(piece.centre[0], 0, piece.centre[1]);
    group.rotation.y = piece.angle;
    const [front,back]=wallSurfaceMaterials(piece,config?.wallFinishes);
    const base=new THREE.MeshStandardMaterial({color:"#cbd9d5"});
    const sides=[front,back].map(finish=>{
      if(!finish)return base;
      if(finish.kind==="tile"&&!wallTile){
        wallTile=floorTexture({kind:"tile",widthM:.6,lengthM:.6});
        textures.push(wallTile);
      }
      return new THREE.MeshStandardMaterial({color:finish.color,map:finish.kind==="tile"?wallTile:null});
    });
    for (const c of piece.chunks) {
      const mesh = new THREE.Mesh(
        wallChunkGeometry(piece,c),
        front||back?[base,base,base,base,...sides]:base,
      );
      mesh.position.set((c.start + c.end - piece.lengthM) / 2, (c.low + c.high) / 2, 0);
      group.add(mesh);
    }
    scene.add(group);
  }
  for (const [i,shape] of yardShapes(m).entries()) {
    const yard=new THREE.Mesh(new THREE.ShapeGeometry(shape),new THREE.MeshStandardMaterial({color:"#839768",side:THREE.DoubleSide}));
    yard.name=`Yard ${i+1}`;
    yard.userData={kind:"garden"};
    yard.position.y=-.01;
    yard.rotation.x=-Math.PI/2;
    scene.add(yard);
  }
  const rooms = [...floorOutlines(m), ...(m.roomZones??[]).map(room=>({
    id:room.id,label:room.label,points:room.polygon.map(p=>({x:p.x*scale,y:p.y*scale})),
  }))];
  const finishes = rooms.map(room=>config && floorMaterialFor(config,room.id));
  const kinds = [...new Set(finishes.flatMap(finish=>finish ? [finish.kind] : []))];
  const photos = new Map(await Promise.all(kinds.map(async kind=>[kind,await loadFloorPhotos(kind)] as const)));
  const surfaces = new Map<string,ReturnType<typeof floorSurface>>();
  for (const [index,r] of rooms.entries()) {
    const shape = new THREE.Shape();
    r.points.forEach((p, i) => (i ? shape.lineTo(p.x, -p.y) : shape.moveTo(p.x, -p.y)));
    shape.closePath();
    const finish = finishes[index];
    let surface;
    if (finish) {
      const key = JSON.stringify([finish.kind,finish.widthM,finish.lengthM]);
      surface = surfaces.get(key);
      if (!surface) {
        surface = floorSurface(finish,photos.get(finish.kind));
        surfaces.set(key,surface);
        textures.push(surface.map);
        if (surface.normalMap) textures.push(surface.normalMap);
        if (surface.roughnessMap) textures.push(surface.roughnessMap);
      }
    }
    const base = config && floorFinishes[config.floorFinish??"default"];
    const mesh = new THREE.Mesh(
      new THREE.ShapeGeometry(shape),
      new THREE.MeshStandardMaterial({color:finish?.color??base?.color??"#e2e6e2",
        roughness:base?.roughness, ...surface, side:THREE.DoubleSide}),
    );
    mesh.name = r.id;
    mesh.userData = { kind:"room", id:r.id, label:r.label, ...(config?{floorFinish:finish??config.floorFinish??"default"}:{}) };
    mesh.rotation.x = -Math.PI / 2;
    scene.add(mesh);
  }
  for (const stair of stairPieces(m)) {
    const group = new THREE.Group();
    group.name = stair.id;
    group.userData = { kind: "stair", id: stair.id };
    const material = new THREE.MeshStandardMaterial({ color: "#a9b9b2" });
    for (const step of stair.steps) {
      const mesh = new THREE.Mesh(new THREE.ExtrudeGeometry(step.shape, { depth: step.height, bevelEnabled: false }), material);
      mesh.rotation.x = -Math.PI / 2;
      group.add(mesh);
    }
    scene.add(group);
  }
  const data = await new GLTFExporter().parseAsync(scene, { binary: true }).finally(()=>textures.forEach(texture=>texture.dispose()));
  const url = URL.createObjectURL(new Blob([data as ArrayBuffer], { type: "model/gltf-binary" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "florp-plan.glb";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
