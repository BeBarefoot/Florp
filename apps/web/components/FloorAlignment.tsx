"use client";

import { useEffect, useState, useRef } from "react";
import type { PointerEvent } from "react";
import { API, request, type Blueprint, type SiteRegion } from "../lib/api";
import { metersPerPixel } from "../lib/plan/derive";
import type { Alignment, PlanResponse } from "../lib/plan/model";
import { SiteOutline } from "./SiteOutline";

function stairCenter(region: SiteRegion, image: Blueprint) {
  const total = region.points.reduce(([x, y], point) => [x + point[0], y + point[1]], [0, 0]);
  return { x: total[0] * image.width / region.points.length, y: total[1] * image.height / region.points.length };
}

export default function FloorAlignment({ first, second, regions, alignment, change }: {
  first: Blueprint;
  second: Blueprint;
  regions: Record<string, SiteRegion[]>;
  alignment?: Alignment | null;
  change: (alignment: Alignment | null) => void;
}) {
  const [opacity, setOpacity] = useState(.5);
  const [zoom, setZoom] = useState(1);
  const [calibratedScale, setCalibratedScale] = useState<number>();
  const [firstStair, setFirstStair] = useState(0);
  const [secondStair, setSecondStair] = useState(0);
  const drag = useRef<{ pointer: number; x: number; y: number; centerX: number; centerY: number } | null>(null);
  const minScale = .001, maxScale = 1000;
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([first.id, second.id].map(id => request<PlanResponse>(`/blueprints/${encodeURIComponent(id)}/plan`, { signal: controller.signal })))
      .then(([ground, upper]) => {
        const a = ground.model && metersPerPixel(ground.model);
        const b = upper.model && metersPerPixel(upper.model);
        if (!controller.signal.aborted && a && b && b / a >= minScale && b / a <= maxScale) setCalibratedScale(b / a);
      }).catch(() => {});
    return () => controller.abort();
  }, [first.id, second.id]);
  const scale = calibratedScale ?? Math.min(first.width / second.width, first.height / second.height);
  const starting = { centerX: first.width / 2, centerY: first.height / 2, rotationDeg: 0,
    scale: Math.min(maxScale, Math.max(minScale, scale)) };
  const current = alignment ?? starting;
  const groundStairs = (regions[first.id] ?? []).filter(region => region.kind === "stairs");
  const upperStairs = (regions[second.id] ?? []).filter(region => region.kind === "stairs");
  const a = groundStairs[firstStair] ?? groundStairs[0];
  const b = upperStairs[secondStair] ?? upperStairs[0];
  const viewWidth = first.width * 1.18 / zoom, viewHeight = first.height * 1.18 / zoom;
  const viewBox = [first.width / 2 - viewWidth / 2, first.height / 2 - viewHeight / 2, viewWidth, viewHeight].join(" ");

  function point(event: PointerEvent<SVGSVGElement>) {
    const matrix = event.currentTarget.getScreenCTM();
    return matrix && new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
  }
  function alignStairs() {
    if (!a || !b) return;
    const ground = stairCenter(a, first), upper = stairCenter(b, second);
    const x = (upper.x - second.width / 2) * current.scale;
    const y = (upper.y - second.height / 2) * current.scale;
    const angle = current.rotationDeg * Math.PI / 180;
    change({ ...current, centerX: ground.x - (x * Math.cos(angle) - y * Math.sin(angle)),
      centerY: ground.y - (x * Math.sin(angle) + y * Math.cos(angle)) });
  }

  return <section id="floor-alignment" className="floor-alignment" aria-labelledby="floor-alignment-title">
    <h3 id="floor-alignment-title">Align floors</h3>
    <p>Drag the upper drawing over the ground floor. Use a shared wall or the stairs as a reference, then save the floor pair.</p>
    {calibratedScale===undefined&&<p>Scale starts from the image sizes. Check a shared dimension when aligning the drawings.</p>}
    <div className="floor-alignment-legend"><span>Ground floor</span><span>Upper floor</span></div>
    <svg className="floor-alignment-overlay" aria-label="Floor alignment overlay" viewBox={viewBox}
      onPointerDown={event => {
        const start = point(event);
        if (!start || event.button !== 0 || !event.isPrimary) return;
        drag.current = { pointer: event.pointerId, x: start.x, y: start.y, centerX: current.centerX, centerY: current.centerY };
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={event => {
        const start = drag.current;
        if (!start || start.pointer !== event.pointerId) return;
        const next = point(event);
        if (next) change({ ...current, centerX: start.centerX + next.x - start.x, centerY: start.centerY + next.y - start.y });
      }}
      onLostPointerCapture={() => { drag.current = null; }}>
      <image href={`${API}/blueprints/${first.id}/preview`} width={first.width} height={first.height}/>
      {a && <g transform={`scale(${first.width} ${first.height})`}><SiteOutline region={a}/></g>}
      <g data-floor-layer="upper" opacity={opacity} transform={`translate(${current.centerX} ${current.centerY}) rotate(${current.rotationDeg}) scale(${current.scale}) translate(${-second.width / 2} ${-second.height / 2})`}>
        <image href={`${API}/blueprints/${second.id}/preview`} width={second.width} height={second.height}/>
        <rect width={second.width} height={second.height} fill="none" stroke="#2e654f" strokeWidth="2" vectorEffect="non-scaling-stroke"/>
        {b && <g transform={`scale(${second.width} ${second.height})`}><SiteOutline region={b}/></g>}
      </g>
    </svg>
    <div className="floor-alignment-controls">
      <label>Move X (px)<input aria-label="Move X (px)" type="number"
        value={Math.round(current.centerX)} onChange={e => Number.isFinite(e.target.valueAsNumber) && change({ ...current, centerX: e.target.valueAsNumber })}/></label>
      <label>Move Y (px)<input aria-label="Move Y (px)" type="number"
        value={Math.round(current.centerY)} onChange={e => Number.isFinite(e.target.valueAsNumber) && change({ ...current, centerY: e.target.valueAsNumber })}/></label>
      <label>Rotation (°)<input type="range" min="-180" max="180" step=".5" value={current.rotationDeg}
        onChange={e => change({ ...current, rotationDeg: e.target.valueAsNumber })}/><span>{current.rotationDeg}°</span></label>
      <label>Upper drawing scale (%)<input type="number" min={minScale * 100} max={maxScale * 100} step="any"
        value={Number((current.scale * 100).toFixed(3))} onChange={e => {
          const scale = e.target.valueAsNumber / 100;
          if (scale >= minScale && scale <= maxScale) change({ ...current, scale });
        }}/></label>
      <label>Upper drawing opacity<input type="range" min=".15" max=".9" step=".05" value={opacity}
        onChange={e => setOpacity(e.target.valueAsNumber)}/></label>
      <label>Zoom<input type="range" min=".4" max="4" step=".1" value={zoom} onChange={e => setZoom(e.target.valueAsNumber)}/></label>
    </div>
    <div className="floor-alignment-actions">
      {calibratedScale !== undefined && <button type="button" onClick={() => change({ ...current, scale: calibratedScale })}>Use measured scale</button>}
      {groundStairs.length > 1 && <label>Ground stair<select value={firstStair} onChange={e => setFirstStair(Number(e.target.value))}>
        {groundStairs.map((_, index) => <option key={index} value={index}>{index + 1}</option>)}
      </select></label>}
      {upperStairs.length > 1 && <label>Upper stair<select value={secondStair} onChange={e => setSecondStair(Number(e.target.value))}>
        {upperStairs.map((_, index) => <option key={index} value={index}>{index + 1}</option>)}
      </select></label>}
      {a && b && <button type="button" onClick={alignStairs}>Align stair centers</button>}
      <button type="button" onClick={() => change(starting)}>Center drawings</button>
    </div>
  </section>;
}
