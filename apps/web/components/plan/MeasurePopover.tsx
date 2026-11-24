"use client";
import { useEffect, useRef, useState } from "react";
import { wallFootprint } from "../../lib/plan/derive";
import type { PlanModel, Pt } from "../../lib/plan/model";

export default function MeasurePopover(p: {
  points: Pt[];
  model: PlanModel;
  toScreen: (p: Pt) => Pt | null;
  pixelsPerMeterNow: number | null;
  checking?: boolean;
  apply: (meters: number) => void;
  cancel: () => void;
}) {
  const [value, setValue] = useState("");
  const [unit, setUnit] = useState<"m" | "cm">("m");
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => input.current?.focus(), []);
  const [a, b] = p.points;
  const pixels = Math.hypot(b.x - a.x, b.y - a.y);
  const at = p.toScreen({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
  if (!at) return null;
  const meters = Number(value) * (unit === "m" ? 1 : 0.01);
  const ref=p.model.scale.reference;
  const samePoint=(a:Pt,b:Pt)=>a.x===b.x&&a.y===b.y;
  const repeated=p.checking&&ref&&((samePoint(a,ref.p1)&&samePoint(b,ref.p2))||
    (samePoint(a,ref.p2)&&samePoint(b,ref.p1)));
  const valid = Number.isFinite(meters) && meters > 0 && meters <= 1000 && pixels >= 5 && !repeated;
  const footprint = valid&&!p.checking ? wallFootprint(p.model, meters / pixels) : null;
  return (
    <form
      className="fe-popover"
      role="dialog"
      aria-label="Known distance"
      style={{ left: at.x, top: at.y }}
      onPointerDown={(e) => e.stopPropagation()}
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) p.apply(meters);
      }}
    >
      <label>
        {p.checking?"Second known length":"Real length"}
        <span className="fe-row">
          <input ref={input} aria-label="Known distance" type="number" min="0.001" step="any" value={value} onChange={(e) => setValue(e.target.value)} />
          <select aria-label="Distance unit" value={unit} onChange={(e) => setUnit(e.target.value as "m" | "cm")}>
            <option value="m">m</option>
            <option value="cm">cm</option>
          </select>
        </span>
      </label>
      {footprint && <p>Building span at this scale: {footprint.width.toFixed(2)} × {footprint.depth.toFixed(2)} m.</p>}
      {footprint?.unusuallySmall && <p role="status">The walls would be taller than the whole footprint is wide or deep. Check the selected endpoints and distance unit.</p>}
      {pixels < 5 && <p className="fe-muted">Pick two points further apart.</p>}
      {repeated && <p role="status">Choose a different distance from the first reference.</p>}
      {p.pixelsPerMeterNow && <p className="fe-muted">Currently {(pixels / p.pixelsPerMeterNow).toFixed(2)} m</p>}
      <span className="fe-row">
        <button type="submit" className="fe-primary" disabled={!valid}>Apply</button>
        <button type="button" onClick={p.cancel}>Cancel</button>
      </span>
    </form>
  );
}
