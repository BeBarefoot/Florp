"use client";
import { useEffect, useRef, useState } from "react";
import type { Pt } from "../../lib/plan/model";

export default function MeasurePopover(p: {
  points: Pt[];
  toScreen: (p: Pt) => Pt | null;
  pixelsPerMeterNow: number | null;
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
  const valid = meters > 0 && pixels >= 5;
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
        Real length
        <span className="fe-row">
          <input ref={input} aria-label="Known distance" type="number" min="0.001" step="any" value={value} onChange={(e) => setValue(e.target.value)} />
          <select aria-label="Distance unit" value={unit} onChange={(e) => setUnit(e.target.value as "m" | "cm")}>
            <option value="m">m</option>
            <option value="cm">cm</option>
          </select>
        </span>
      </label>
      {pixels < 5 && <p className="fe-muted">Pick two points further apart.</p>}
      {p.pixelsPerMeterNow && <p className="fe-muted">Currently {(pixels / p.pixelsPerMeterNow).toFixed(2)} m</p>}
      <span className="fe-row">
        <button type="submit" className="fe-primary" disabled={!valid}>Apply</button>
        <button type="button" onClick={p.cancel}>Cancel</button>
      </span>
    </form>
  );
}
