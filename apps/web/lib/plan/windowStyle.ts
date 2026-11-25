import type {Opening, WindowFrame} from "./model";

export const windowFrameDefaults = {
  aluminium: "#d9d8d1",
  wood: "#a77852",
  vinyl: "#f2f1eb",
} satisfies Record<WindowFrame["material"],string>;

export const windowFrameFor = (opening: Opening): WindowFrame => opening.windowFrame ??
  {material:"aluminium",color:windowFrameDefaults.aluminium,widthM:.05,panes:1};
