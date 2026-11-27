import * as THREE from "three";
import { GLTFExporter } from "three/examples/jsm/exporters/GLTFExporter.js";
import type { PlanModel } from "./plan/model";
import { metersPerPixel } from "./plan/derive";
import { wallPieces } from "./plan/mesh";
import { roomsOf } from "./plan/walkSpace";
import {yardColor,yardShapes} from "./plan/yard";
import { roomSurfaces, stairPieces } from "./plan/stairs";
import {stairCutouts} from "./plan/stairLevels";
import { makeWindows } from "./plan/windowFrames";
import { doorLeaves } from "./plan/doorLeaves";
import { floorMaterialFor, floorSurface, floorTexture, loadFloorPhotos } from "./plan/floorMaterials";
import { floorFinishes, type Scene } from "./plan/scene";
import {furnitureParts,makeFurnitureResources} from "./plan/furnitureModels";
import {loadFurnitureAsset,scaledFurnitureAsset} from "./plan/furnitureAssets";
import {homePresets, presetFloor} from "./plan/homePresets";
import {objectName} from "./plan/furnitureCatalog";
import { wallChunkGeometry, wallSurfaceMaterials } from "./plan/wallMaterials";

/** Metric glTF (meters) with stable wall/room/opening IDs in node extras. */
export async function exportPlan3D(m: PlanModel, review: unknown = {status:"draft"}, config?: Scene) {
  const scale = metersPerPixel(m);
  if (!scale) throw Error("Set one measurement first");
  if (m.openings.some((o) => o.status === "proposed"))
    throw Error("Approve or reject every proposed door and window before exporting 3D.");
  const scene = new THREE.Scene();
  const designPreset=config?.designPreset;
  const preset=designPreset?homePresets[designPreset]:undefined;
  const textures: THREE.Texture[] = [];
  let wallTile: THREE.Texture|null=null;
  scene.userData = {planRevision:m.revision, architectureReview:review,designPreset};
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
    const base=new THREE.MeshStandardMaterial({color:preset?.wall??"#cbd9d5"});
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
  for (const [i,{shape,surface}] of yardShapes(m).entries()) {
    const yard=new THREE.Mesh(new THREE.ShapeGeometry(shape),new THREE.MeshStandardMaterial({color:yardColor[surface],side:THREE.DoubleSide}));
    yard.name=`${surface==="paving"?"Patio":"Yard"} ${i+1}`;
    yard.userData={kind:"garden",surface};
    yard.position.y=-.01;
    yard.rotation.x=-Math.PI/2;
    scene.add(yard);
  }
  const rooms=roomsOf(m);
  const cutouts=stairCutouts(m);
  const finishes = rooms.map(room=>(config && floorMaterialFor(config,room.id)) ?? presetFloor(designPreset,room.roomType));
  const kinds = [...new Set(finishes.flatMap(finish=>finish ? [finish.kind] : []))];
  const photos = new Map(await Promise.all(kinds.map(async kind=>[kind,await loadFloorPhotos(kind)] as const)));
  const surfaces = new Map<string,ReturnType<typeof floorSurface>>();
  for (const [index,r] of rooms.entries()) {
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
    const shapes=roomSurfaces(r.polygon,scale,cutouts);
    if(!shapes.length)continue;
    const mesh = new THREE.Mesh(
      new THREE.ShapeGeometry(shapes),
      new THREE.MeshStandardMaterial({color:finish?.color??base?.color??"#e2e6e2",
        roughness:base?.roughness, ...surface, side:THREE.DoubleSide}),
    );
    mesh.name = r.id;
    mesh.userData = { kind:"room", id:r.id, label:r.label, ...(config?{floorFinish:finish??config.floorFinish??"default"}:{}) };
    mesh.rotation.x = -Math.PI / 2;
    scene.add(mesh);
  }
  const stairs=stairPieces(m);
  for (const stair of stairs) {
    const group = new THREE.Group();
    group.name = stair.id;
    group.userData = { kind: "stair", id: stair.id, direction:stair.direction };
    const material = new THREE.MeshStandardMaterial({ color: "#a39b8d", roughness:.83 });
    const treadMaterial=new THREE.MeshStandardMaterial({color:"#c6a681",roughness:.68});
    for (const step of stair.steps) {
      const mesh = new THREE.Mesh(new THREE.ExtrudeGeometry(step.shape, { depth: step.height, bevelEnabled: false }), material);
      mesh.rotation.x = -Math.PI / 2;
      mesh.position.y=step.bottom;
      group.add(mesh);
      const tread=new THREE.Mesh(new THREE.ShapeGeometry(step.shape),treadMaterial);
      tread.rotation.x=-Math.PI/2;
      tread.position.y=step.bottom+step.height+.001;
      group.add(tread);
    }
    for(const well of stair.wells){
      group.add(new THREE.Mesh(well.walls,new THREE.MeshStandardMaterial({color:"#aeaba0",side:THREE.DoubleSide})));
      const bottom=new THREE.Mesh(new THREE.ShapeGeometry(well.shape),new THREE.MeshStandardMaterial({color:"#958d80"}));
      bottom.position.y=well.bottom;
      bottom.rotation.x=-Math.PI/2;
      group.add(bottom);
    }
    scene.add(group);
  }
  const windows=makeWindows(m,null,false,preset?.frame);
  scene.add(windows.group);
  for (const door of doorLeaves(m,scale,config?.closedDoorIds)) {
    const leaf=new THREE.Mesh(new THREE.BoxGeometry(door.length,door.height,.04),
      new THREE.MeshStandardMaterial({color:preset?.door??"#b9a58d",roughness:.62}));
    leaf.name=door.id;
    leaf.userData={kind:"door",id:door.id};
    leaf.position.set(door.x+Math.cos(door.angle)*door.length/2,door.height/2,
      door.z-Math.sin(door.angle)*door.length/2);
    leaf.rotation.y=door.angle;
    scene.add(leaf);
  }
  const furniture=makeFurnitureResources(designPreset);
  const items=config?.objects??[];
  const assets=new Map(await Promise.all([...new Set(items.map(item=>item.kind))].map(async kind=>
    [kind,designPreset?null:await loadFurnitureAsset(kind)] as const
  )));
  for (const item of items) {
    const group=new THREE.Group();
    group.name=objectName(item.kind);
    group.userData={kind:"furniture",id:item.id,product:item.kind};
    group.position.set(item.position.x*scale,0,item.position.y*scale);
    group.rotation.y=-item.rotation*Math.PI/180;
    const asset=assets.get(item.kind);
    if(asset) group.add(scaledFurnitureAsset(asset,item));
    else for (const part of furnitureParts(item,designPreset)) {
      const mesh=new THREE.Mesh(furniture.geometry(part.shape),furniture.material(part.finish));
      mesh.position.set(...part.position);
      mesh.scale.set(...part.size);
      if(part.turn)mesh.rotation.set(...part.turn);
      group.add(mesh);
    }
    scene.add(group);
  }
  const data = await new GLTFExporter().parseAsync(scene, { binary: true }).finally(()=>{
    textures.forEach(texture=>texture.dispose());
    furniture.dispose();
    windows.dispose();
    stairs.forEach(stair=>stair.wells.forEach(well=>well.walls.dispose()));
  });
  const url = URL.createObjectURL(new Blob([data as ArrayBuffer], { type: "model/gltf-binary" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "florp-plan.glb";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
