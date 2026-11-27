import type {WindowFrame} from "./model";
import type {FloorMaterial} from "./scene";

type Preset = {
  name: string; wall: string; floor: FloorMaterial; wet: string; door: string;
  frame: Pick<WindowFrame, "material" | "color">;
  timber: string; fabric: string; metal: string; stone: string;
};
const finish = (kind: FloorMaterial["kind"], color: string, widthM: number, lengthM: number) =>
  ({kind, color, widthM, lengthM});

export const homePresets = {
  hotel: {name:"Boutique hotel",wall:"#ece4d7",floor:finish("wood","#986346",.22,1.5),wet:"#e9dfcc",door:"#553a2d",
    frame:{material:"aluminium",color:"#50423a"},timber:"#694736",fabric:"#cfb59d",metal:"#a88756",stone:"#e4d6be"},
  country: {name:"Country house",wall:"#f3eada",floor:finish("wood","#b18251",.24,1.6),wet:"#c9b49a",door:"#996d43",
    frame:{material:"wood",color:"#997046"},timber:"#9a6842",fabric:"#c7baa1",metal:"#8c7349",stone:"#dcc6a7"},
  monochrome: {name:"Black & white",wall:"#f2f0eb",floor:finish("tile","#d7d6d2",.9,.9),wet:"#b5b6b4",door:"#25282a",
    frame:{material:"aluminium",color:"#2d3032"},timber:"#363939",fabric:"#ecebea",metal:"#55595b",stone:"#d9d9d5"},
  plain: {name:"Plain",wall:"#f0efeb",floor:finish("concrete","#d9d7cf",1,1),wet:"#d9d7cf",door:"#d3c8b7",
    frame:{material:"vinyl",color:"#f1efea"},timber:"#a59886",fabric:"#e0ded7",metal:"#a1a4a2",stone:"#dedbd5"},
  scandinavian: {name:"Scandinavian",wall:"#f3eee5",floor:finish("wood","#d6b28d",.19,1.25),wet:"#e4ddce",door:"#bd9770",
    frame:{material:"wood",color:"#c2a282"},timber:"#b08961",fabric:"#e3d9c9",metal:"#827b65",stone:"#ded6c8"},
  mediterranean: {name:"Mediterranean",wall:"#f3e5d2",floor:finish("tile","#be8a65",.4,.4),wet:"#aec3b3",door:"#83583c",
    frame:{material:"wood",color:"#8c644a"},timber:"#875c42",fabric:"#ddc6a9",metal:"#92775d",stone:"#eddbbc"},
} satisfies Record<string, Preset>;
export type HomePreset = keyof typeof homePresets;

export function presetFloor(preset: HomePreset | null | undefined, roomType?: string | null): FloorMaterial | undefined {
  if (!preset || roomType === "balcony") return undefined;
  const style = homePresets[preset];
  return roomType === "bathroom" ? finish("tile", style.wet, .6, .6) : style.floor;
}
