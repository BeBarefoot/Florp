import type {Opening, WindowFrame} from "./model";
import type {WindowFinish} from "./scene";

export const windowFrameDefaults = {
  aluminium: "#d9d8d1",
  wood: "#a77852",
  vinyl: "#f2f1eb",
} satisfies Record<WindowFrame["material"],string>;

export const windowFrameFor = (opening: Opening): WindowFrame => opening.windowFrame ??
  {material:"aluminium",color:windowFrameDefaults.aluminium,widthM:.05,panes:1};

export function styledWindowFrame(opening:Opening,preset?:WindowFinish,override?:WindowFinish):WindowFrame {
  const frame=windowFrameFor(opening);
  return {...frame,...(!opening.windowFrame?preset:undefined),...override};
}
