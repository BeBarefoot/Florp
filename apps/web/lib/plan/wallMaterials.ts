import { BoxGeometry } from "three";
import type { Chunk, WallPiece } from "./mesh";
import type { Scene, WallSide } from "./scene";

export const otherSide = (side: WallSide): WallSide => side==="a"?"b":"a";

export function wallSurfaceMaterials(piece:WallPiece, finishes:Scene["wallFinishes"]){
  const wall=finishes&&Object.hasOwn(finishes,piece.id)?finishes[piece.id]:undefined;
  return [wall?.[piece.positiveSide],wall?.[otherSide(piece.positiveSide)]] as const;
}

export function wallChunkGeometry(piece:WallPiece, chunk:Chunk){
  const geometry=new BoxGeometry(chunk.end-chunk.start,chunk.high-chunk.low,piece.thicknessM);
  const uv=geometry.getAttribute("uv");
  const positions=geometry.getAttribute("position");
  // The last two BoxGeometry groups are the broad faces at +Z and -Z.
  // Use metres from the canonical wall start so tiling continues around openings.
  for(let index=16;index<24;index++){
    const along=positions.getX(index)+(chunk.start+chunk.end)/2;
    uv.setXY(index,piece.positiveSide==="a"?along:piece.lengthM-along,
      positions.getY(index)+(chunk.low+chunk.high)/2);
  }
  return geometry;
}
