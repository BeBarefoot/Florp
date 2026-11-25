import {Box3,Group,Vector3} from "three";
import {GLTFLoader} from "three/addons/loaders/GLTFLoader.js";
import type {ObjectKind} from "./furnitureCatalog";
import {itemBottom,type Item} from "./scene";

const files: Partial<Record<ObjectKind,string>> = {
  sofa:"sofa",
  rug:"rug",
  console_standing:"console",
  toilet:"toilet",
  vanity:"vanity",
  shower:"shower",
};

type FurnitureAsset = {scene:Group;size:Vector3;origin:Vector3};
const requests = new Map<string,Promise<FurnitureAsset|null>>();

export function loadFurnitureAsset(kind:ObjectKind):Promise<FurnitureAsset|null> {
  const name = files[kind];
  if (!name) return Promise.resolve(null);
  const requested = requests.get(name);
  if (requested) return requested;
  const request = new GLTFLoader().loadAsync(`/furniture/${name}.glb`).then(({scene})=>{
    const box = new Box3().setFromObject(scene,true);
    const size = box.getSize(new Vector3());
    const origin = box.getCenter(new Vector3());
    origin.y = box.min.y;
    if (![size.x,size.y,size.z].every(value=>Number.isFinite(value)&&value>0)) throw Error("Invalid furniture bounds");
    return {scene,size,origin};
  }).catch(()=>{
    requests.delete(name);
    return null;
  });
  requests.set(name,request);
  return request;
}

export function scaledFurnitureAsset(asset:FurnitureAsset,item:Pick<Item,"kind"|"width"|"height"|"depth">) {
  const model = asset.scene.clone();
  const centered = new Group();
  centered.add(model);
  centered.position.copy(asset.origin).negate();
  const fit = new Group();
  fit.add(centered);
  fit.scale.set(item.width/asset.size.x,item.height/asset.size.y,item.depth/asset.size.z);
  fit.position.y = itemBottom(item);
  return fit;
}
