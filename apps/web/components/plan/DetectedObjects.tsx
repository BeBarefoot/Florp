import type {PlanModel} from "../../lib/plan/model";
import {objectName, dimensions} from "../../lib/plan/furnitureCatalog";
import {detectedKinds, hasDetectedFootprint} from "../../lib/plan/detectedFurniture";
import {furnitureParts, furnitureColor} from "../../lib/plan/furnitureModels";

export default function DetectedObjects({plan}: {plan: PlanModel}) {
  return <g pointerEvents="none" aria-label="Detected objects">
    {(plan.roomSymbols ?? []).map((symbol, index) => {
      if (!hasDetectedFootprint(symbol)) return null;
      const kind = detectedKinds[symbol.kind];
      const width = symbol.widthPx!;
      const depth = symbol.depthPx!;
      // Project the same parts as the 3D object. The source footprint is
      // already in plan pixels, so it can be shown before calibration.
      const parts = furnitureParts({
        kind, id: String(index), position: symbol.position, width, depth,
        height: dimensions(kind).height, rotation: symbol.rotation ?? 0,
      }).sort((a, b) => a.position[1] + a.size[1] / 2 - b.position[1] - b.size[1] / 2);
      return <g key={index} data-detected-object={symbol.kind} role="img" aria-label={objectName(kind)}
        transform={`translate(${symbol.position.x} ${symbol.position.y}) rotate(${symbol.rotation ?? 0})`}>
        {parts.map(({position, size, finish, shape, turn}, partIndex) => {
          const [x, , y] = position;
          const [w, , d] = size;
          const color = furnitureColor(finish);
          const angle = -(turn?.[1] ?? 0) * 180 / Math.PI;
          const strokeWidth = Math.min(width, depth) * .014;
          return shape === "sphere" || shape === "tube" || shape === "bowl" || shape === "pot" ?
            <ellipse key={partIndex} cx={x} cy={y} rx={w / 2} ry={d / 2}
              fill={color} stroke="#34443d" strokeWidth={strokeWidth}/> :
            <rect key={partIndex} x={x - w / 2} y={y - d / 2} width={w} height={d}
              rx={shape === "box" ? 0 : Math.min(w, d) * .14} fill={color}
              stroke="#34443d" strokeWidth={strokeWidth}
              transform={angle ? `rotate(${angle} ${x} ${y})` : undefined}/>;
        })}
      </g>;
    })}
  </g>;
}
