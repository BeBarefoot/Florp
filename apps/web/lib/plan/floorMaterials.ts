import { CanvasTexture, ImageLoader, RepeatWrapping, SRGBColorSpace, Texture } from "three";
import type { FloorMaterial, Scene } from "./scene";

export function unmatchedFloorFinishes(scene: Pick<Scene,"roomFloorMaterials">, rooms: {id:string}[]) {
  const ids = new Set(rooms.map(room=>room.id));
  return Object.entries(scene.roomFloorMaterials??{}).filter(([id])=>!ids.has(id));
}

export const materialDefaults: Record<FloorMaterial["kind"], FloorMaterial> = {
  wood: {kind:"wood", color:"#bf946d", widthM:.18, lengthM:1.2},
  concrete: {kind:"concrete", color:"#a9a6a0", widthM:1, lengthM:1},
  marble: {kind:"marble", color:"#e4dac6", widthM:.6, lengthM:.6},
  tile: {kind:"tile", color:"#c8bca7", widthM:.3, lengthM:.6},
};

export function floorMaterialFor(scene: Pick<Scene,"floorFinish"|"floorMaterial"|"roomFloorMaterials">, roomId: string) {
  const overrides = scene.roomFloorMaterials;
  if (overrides && Object.hasOwn(overrides,roomId)) return overrides[roomId];
  return scene.floorMaterial ?? (scene.floorFinish === "oak" ? materialDefaults.wood : null);
}

const photoRepeats = {wood: [4, 8], marble: [4, 4], tile: [5, 5]} as const;
export type PhotoFloor = keyof typeof photoRepeats;
type PhotoMaps = Texture[];
const photoLoads = new Map<PhotoFloor, Promise<PhotoMaps | null>>();

function hasFloorPhotos(kind:FloorMaterial["kind"]):kind is PhotoFloor {
  return Object.hasOwn(photoRepeats,kind);
}

export function loadFloorPhotos(kind: FloorMaterial["kind"]) {
  if (!hasFloorPhotos(kind)) return Promise.resolve(null);
  const pending = photoLoads.get(kind);
  if (pending) return pending;

  const loader = new ImageLoader();
  const load = Promise.all([
    loader.loadAsync(`/materials/floors/${kind}-color.webp`),
    loader.loadAsync(`/materials/floors/${kind}-normal.webp`),
    loader.loadAsync(`/materials/floors/${kind}-roughness.webp`),
  ]).then(images=>images.map(image=>new Texture(image))).catch(() => {
    photoLoads.delete(kind);
    return null;
  });
  photoLoads.set(kind, load);
  return load;
}

export function floorSurface({kind, widthM, lengthM}: FloorMaterial, photos: PhotoMaps | null = null) {
  const material = {kind, widthM, lengthM};
  if (!photos || !hasFloorPhotos(kind)) {
    return {
      map: floorTexture(material),
      normalMap: null,
      roughnessMap: null,
      roughness: kind === "marble" ? .4 : .75,
    };
  }
  const [columns, rows] = photoRepeats[kind];
  const [map, normalMap, roughnessMap] = photos.map(source => {
    const texture = source.clone();
    texture.wrapS = texture.wrapT = RepeatWrapping;
    texture.repeat.set(1 / (columns * lengthM), 1 / (rows * widthM));
    texture.anisotropy = 8;
    texture.needsUpdate = true;
    return texture;
  });
  map.colorSpace = SRGBColorSpace;
  return {map, normalMap, roughnessMap, roughness: 1};
}

// Floor shape UVs are in metres. One image spans the specified tile or a pair of staggered planks.
export function floorTexture({kind,widthM,lengthM}: Omit<FloorMaterial, "color">) {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 128;
  const ctx = canvas.getContext("2d")!;
  const image = ctx.createImageData(128,128);
  for (let y=0; y<128; y++) {
    for (let x=0; x<128; x++) {
      const grain = Math.sin(y * .84 + Math.sin(x * Math.PI / 64) * 1.5);
      let tone = 245 + ((x * 19 + y * 53) % 11) - 5;
      if (kind === "wood") {
        tone = y % 64 === 0 || x === (y < 64 ? 0 : 64) ? 157 : 231 + grain * 11 + (y < 64 ? 7 : 0);
      } else if (kind === "marble") {
        const vein = Math.abs(Math.sin((x + y) * Math.PI / 64 + Math.sin(y * Math.PI / 64) * .9));
        tone -= 66 * Math.exp(-vein * 16);
      }
      if ((kind === "tile" || kind === "marble") && (x < 1 || y < 1)) tone = 174;
      image.data.set([tone,tone,tone,255],(y*128+x)*4);
    }
  }
  ctx.putImageData(image,0,0);
  const texture = new CanvasTexture(canvas);
  texture.wrapS = texture.wrapT = RepeatWrapping;
  texture.repeat.set(1/lengthM,1/(widthM*(kind === "wood" ? 2 : 1)));
  texture.colorSpace = SRGBColorSpace;
  texture.anisotropy = 4;
  return texture;
}
