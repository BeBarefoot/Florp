"use client";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { Finding, Opening, PlanModel, Pt } from "../../lib/plan/model";
import { metersPerPixel, nodeMap, openingEnds, wallEnds } from "../../lib/plan/derive";
import { addOpening, addWall, attachOpening, moveNode, patchOpening } from "../../lib/plan/ops";
import type { Focus, Selection, Tool, ViewMode } from "./types";

type Box = { x: number; y: number; w: number; h: number };
type Drag =
  | { kind: "pan"; start: Pt; box: Box; scale: number; room: string | null; moved: boolean }
  | { kind: "node"; id: string }
  | { kind: "opening"; id: string; part: "move" | "start" | "end"; grab: number }
  | { kind: "measure"; index: number }
  | { kind: "outline"; index: number }
  | null;

const COLORS = { wall: "#24414d", selected: "#e08a2c", window: "#3fb4c4", room: "#eef6f2", roomSel: "#d2ece3" };

export default function PlanCanvas(props: {
  model: PlanModel;
  imageUrl: string;
  view: ViewMode;
  tool: Tool;
  setTool: (t: Tool) => void;
  selection: Selection;
  select: (s: Selection) => void;
  activeFinding: Finding | null;
  measure: Pt[];
  setMeasure: (p: Pt[]) => void;
  corners: Pt[];
  setCorners: (p: Pt[]) => void;
  edit: (next: PlanModel, history?: boolean) => void;
  checkpoint: () => void;
  fail: (message: string) => void;
  fitNonce: number;
  focus: Focus;
  outline?: Pt[] | null;
  setOutline?: (p: Pt[]) => void;
  commitOutline?: (p: Pt[]) => void;
  children?: (helpers: { toScreen: (p: Pt) => Pt | null }) => React.ReactNode;
}) {
  const { model: m, tool, selection } = props;
  const W = m.imageTransform.width,
    H = m.imageTransform.height;
  const svg = useRef<SVGSVGElement>(null);
  const host = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState<Box>({ x: 0, y: 0, w: W, h: H });
  const [pointer, setPointer] = useState<Pt | null>(null);
  const [draft, setDraft] = useState<Pt | null>(null);
  const [hover, setHover] = useState<Selection>(null);
  const drag = useRef<Drag>(null);
  const nodes = useMemo(() => nodeMap(m), [m]);
  const mpp = metersPerPixel(m);
  const fit = () => {
    const pad = Math.max(W, H) * 0.04;
    setBox({ x: -pad, y: -pad, w: W + 2 * pad, h: H + 2 * pad });
  };
  useLayoutEffect(fit, [W, H, props.fitNonce]);
  useEffect(() => {
    if (!props.focus) return;
    const w = Math.min(box.w, W / 2.5),
      h = (w * box.h) / box.w;
    setBox({ x: props.focus.point.x - w / 2, y: props.focus.point.y - h / 2, w, h });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.focus?.nonce]);
  useEffect(() => {
    setDraft(null);
  }, [tool]);
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      const p = toSvg(e.clientX, e.clientY);
      const f = Math.exp(Math.max(-0.5, Math.min(0.5, e.deltaY * 0.0015)));
      setBox((b) => {
        const w = Math.max(W / 40, Math.min(W * 6, b.w * f));
        const k = w / b.w;
        return { x: p.x - (p.x - b.x) * k, y: p.y - (p.y - b.y) * k, w, h: b.h * k };
      });
    };
    el.addEventListener("wheel", wheel, { passive: false });
    return () => el.removeEventListener("wheel", wheel);
  });

  function toSvg(cx: number, cy: number): Pt {
    const ctm = svg.current?.getScreenCTM();
    if (!ctm) return { x: 0, y: 0 };
    const p = new DOMPoint(cx, cy).matrixTransform(ctm.inverse());
    return { x: p.x, y: p.y };
  }
  function toScreen(p: Pt): Pt | null {
    const ctm = svg.current?.getScreenCTM();
    const rect = host.current?.getBoundingClientRect();
    if (!ctm || !rect) return null;
    const q = new DOMPoint(p.x, p.y).matrixTransform(ctm);
    return { x: q.x - rect.left, y: q.y - rect.top };
  }
  const clamp = (p: Pt): Pt => ({ x: Math.max(0, Math.min(W, p.x)), y: Math.max(0, Math.min(H, p.y)) });
  const px = box.w / Math.max(1, host.current?.clientWidth || 1000);
  const axisSnap = (from: Pt, p: Pt, shift: boolean) =>
    !shift ? p : Math.abs(p.x - from.x) > Math.abs(p.y - from.y) ? { x: p.x, y: from.y } : { x: from.x, y: p.y };

  function down(e: React.PointerEvent<SVGSVGElement>) {
    const p = clamp(toSvg(e.clientX, e.clientY));
    if (e.button === 1 || tool === "select" || tool === "attach") {
      const ctm = svg.current!.getScreenCTM()!;
      const room = (e.target as Element).closest?.("[data-kind=room]")?.getAttribute("data-id") || null;
      drag.current = { kind: "pan", start: { x: e.clientX, y: e.clientY }, box, scale: ctm.a, room, moved: false };
      svg.current!.setPointerCapture(e.pointerId);
      return;
    }
    if (tool === "straighten") {
      if (props.corners.length < 4) props.setCorners([...props.corners, p]);
      return;
    }
    if (tool === "measure") {
      if (props.measure.length !== 1) props.setMeasure([p]);
      else props.setMeasure([props.measure[0], axisSnap(props.measure[0], p, e.shiftKey)]);
      return;
    }
    if (!draft) {
      setDraft(p);
      return;
    }
    const end = axisSnap(draft, p, e.shiftKey);
    setDraft(null);
    if (Math.hypot(end.x - draft.x, end.y - draft.y) < 3) return;
    if (tool === "wall") {
      const t = m.walls.length ? m.walls.map((w) => w.thicknessPx).sort((a, b) => a - b)[m.walls.length >> 1] : 8;
      const r = addWall(m, draft, end, t, Math.max(6, 10 * px));
      if (r.wallId) {
        props.edit(r.model);
        props.select({ type: "wall", id: r.wallId });
      }
      return;
    }
    if (tool === "door" || tool === "window") {
      const r = addOpening(m, tool, draft, end);
      if (!r) return props.fail("Draw the opening along a wall.");
      props.edit(r.model);
      props.select({ type: "opening", id: r.openingId });
      props.setTool("select");
    }
  }
  function move(e: React.PointerEvent<SVGSVGElement>) {
    const raw = toSvg(e.clientX, e.clientY);
    const p = clamp(raw);
    setPointer(p);
    const d = drag.current;
    if (!d) return;
    if (d.kind === "pan") {
      const dx = (e.clientX - d.start.x) / d.scale,
        dy = (e.clientY - d.start.y) / d.scale;
      if (!d.moved && Math.hypot(e.clientX - d.start.x, e.clientY - d.start.y) < 4) return;
      d.moved = true;
      setBox({ ...d.box, x: d.box.x - dx, y: d.box.y - dy });
    } else if (d.kind === "node") {
      props.edit(moveNode(m, d.id, p), false);
    } else if (d.kind === "outline" && props.outline) {
      props.setOutline?.(props.outline.map((q, i) => (i === d.index ? p : q)));
    } else if (d.kind === "measure") {
      props.setMeasure(props.measure.map((q, i) => (i === d.index ? p : q)));
    } else if (d.kind === "opening") {
      const o = m.openings.find((x) => x.id === d.id);
      const w = o && m.walls.find((x) => x.id === o.hostWallId);
      if (!o || !w) return;
      const [a, b] = wallEnds(m, w, nodes);
      const l = Math.hypot(b.x - a.x, b.y - a.y) || 1;
      const t = ((p.x - a.x) * (b.x - a.x) + (p.y - a.y) * (b.y - a.y)) / l;
      let next: Partial<Opening>;
      if (d.part === "move") next = { offsetPx: t - d.grab };
      else if (d.part === "start") {
        const endPx = o.offsetPx + o.widthPx;
        const s = Math.min(t, endPx - 4);
        next = { offsetPx: Math.max(0, s), widthPx: endPx - Math.max(0, s) };
      } else next = { widthPx: Math.max(4, Math.min(l - o.offsetPx, t - o.offsetPx)) };
      props.edit(patchOpening(m, o.id, next), false);
    }
  }
  function up() {
    const d = drag.current;
    if (d?.kind === "pan" && !d.moved && tool === "select")
      props.select(d.room ? { type: "room", id: d.room } : null);
    if (d?.kind === "outline" && props.outline) props.commitOutline?.(props.outline);
    drag.current = null;
  }
  function startDrag(e: React.PointerEvent, d: Drag) {
    e.stopPropagation();
    if (d && d.kind !== "measure" && d.kind !== "outline") props.checkpoint();
    drag.current = d;
    svg.current!.setPointerCapture(e.pointerId);
  }
  function pickWall(e: React.PointerEvent, id: string) {
    if (tool === "attach" && selection?.type === "opening") {
      e.stopPropagation();
      const next = attachOpening(m, selection.id, id);
      if (!next) return props.fail("That wall is not aligned with this opening.");
      props.edit(next);
      props.setTool("select");
      return;
    }
    if (tool !== "select") return;
    e.stopPropagation();
    props.select({ type: "wall", id });
  }

  const selWall = selection?.type === "wall" ? m.walls.find((w) => w.id === selection.id) : undefined;
  const selOpening = selection?.type === "opening" ? m.openings.find((o) => o.id === selection.id) : undefined;
  const handleR = 6 * px;
  const rubberFrom = tool === "measure" && props.measure.length === 1 ? props.measure[0] : draft;
  const showFinding =
    props.activeFinding ||
    (selection && m.findings.find((f) => f.targetIds.includes(selection.id) || (selWall && (f.targetIds.includes(selWall.a) || f.targetIds.includes(selWall.b))))) ||
    null;

  return (
    <div className="fe-canvas" ref={host} data-tool={tool}>
      <svg
        ref={svg}
        viewBox={`${box.x} ${box.y} ${box.w} ${box.h}`}
        preserveAspectRatio="xMidYMid meet"
        onPointerDown={down}
        onPointerMove={move}
        onPointerUp={up}
        onPointerLeave={() => setPointer(null)}
        aria-label="Plan drawing"
      >
        <rect x={0} y={0} width={W} height={H} fill="white" className="fe-sheet" />
        {props.view !== "clean" && (
          <image href={props.imageUrl} width={W} height={H} opacity={props.view === "overlay" ? 0.45 : 1} />
        )}
        {props.view !== "original" && (
          <g>
            {m.rooms.map((r) => (
              <polygon
                key={r.id}
                data-kind="room"
                data-id={r.id}
                points={r.polygon.map((p) => `${p.x},${p.y}`).join(" ")}
                fill={selection?.id === r.id ? COLORS.roomSel : COLORS.room}
              />
            ))}
            {m.walls.map((w) => {
              const [a, b] = wallEnds(m, w, nodes);
              const active = selection?.id === w.id || hover?.id === w.id;
              return (
                <g key={w.id}>
                  <line
                    data-kind="wall"
                    data-id={w.id}
                    x1={a.x}
                    y1={a.y}
                    x2={b.x}
                    y2={b.y}
                    stroke={selection?.id === w.id ? COLORS.selected : COLORS.wall}
                    strokeOpacity={w.confidence < 0.6 && !active ? 0.7 : 1}
                    strokeWidth={w.thicknessPx}
                    strokeLinecap="square"
                  />
                  <line
                    x1={a.x}
                    y1={a.y}
                    x2={b.x}
                    y2={b.y}
                    stroke={hover?.id === w.id && selection?.id !== w.id ? "#e08a2c55" : "transparent"}
                    strokeWidth={Math.max(w.thicknessPx, 12 * px)}
                    onPointerEnter={() => setHover({ type: "wall", id: w.id })}
                    onPointerLeave={() => setHover(null)}
                    onPointerDown={(e) => pickWall(e, w.id)}
                  />
                </g>
              );
            })}
            {m.openings.map((o) => (
              <OpeningSymbol
                key={o.id}
                m={m}
                o={o}
                px={px}
                selected={selection?.id === o.id}
                onDown={(e) => {
                  if (tool !== "select") return;
                  e.stopPropagation();
                  props.select({ type: "opening", id: o.id });
                }}
              />
            ))}
          </g>
        )}
        {selWall &&
          tool === "select" &&
          [selWall.a, selWall.b].map((id) => {
            const n = nodes.get(id)!;
            return (
              <circle
                key={id}
                data-testid="node-handle"
                className="fe-handle"
                cx={n.x}
                cy={n.y}
                r={handleR}
                strokeWidth={2 * px}
                onPointerDown={(e) => startDrag(e, { kind: "node", id })}
              />
            );
          })}
        {selOpening && selOpening.hostWallId && tool === "select" && (() => {
          const ends = openingEnds(m, selOpening, nodes)!;
          const mid = { x: (ends[0].x + ends[1].x) / 2, y: (ends[0].y + ends[1].y) / 2 };
          return (
            <g>
              {(["start", "end"] as const).map((part, i) => (
                <rect
                  key={part}
                  className="fe-handle"
                  x={ends[i].x - handleR * 0.8}
                  y={ends[i].y - handleR * 0.8}
                  width={handleR * 1.6}
                  height={handleR * 1.6}
                  strokeWidth={2 * px}
                  onPointerDown={(e) => startDrag(e, { kind: "opening", id: selOpening.id, part, grab: 0 })}
                />
              ))}
              <circle
                className="fe-handle"
                cx={mid.x}
                cy={mid.y}
                r={handleR}
                strokeWidth={2 * px}
                onPointerDown={(e) => {
                  const w = m.walls.find((x) => x.id === selOpening.hostWallId)!;
                  const [a, b] = wallEnds(m, w, nodes);
                  const l = Math.hypot(b.x - a.x, b.y - a.y) || 1;
                  const p = toSvg(e.clientX, e.clientY);
                  const t = ((p.x - a.x) * (b.x - a.x) + (p.y - a.y) * (b.y - a.y)) / l;
                  startDrag(e, { kind: "opening", id: selOpening.id, part: "move", grab: t - selOpening.offsetPx });
                }}
              />
            </g>
          );
        })()}
        {props.outline && (
          <g data-testid="building-outline">
            <polygon
              points={props.outline.map((p) => `${p.x},${p.y}`).join(" ")}
              fill="none"
              stroke="#2f9e44"
              strokeWidth={2 * px}
              strokeDasharray={`${6 * px} ${4 * px}`}
              pointerEvents="none"
            />
            {props.outline.map((p, i) => (
              <circle
                key={i}
                data-testid="outline-handle"
                className="fe-handle"
                cx={p.x}
                cy={p.y}
                r={handleR}
                strokeWidth={2 * px}
                onPointerDown={(e) => startDrag(e, { kind: "outline", index: i })}
              />
            ))}
          </g>
        )}
        {showFinding && (
          <circle
            data-testid="finding-indicator"
            cx={showFinding.anchor.x}
            cy={showFinding.anchor.y}
            r={14 * px}
            fill="none"
            stroke="#d9480f"
            strokeWidth={2.5 * px}
            strokeDasharray={`${4 * px} ${3 * px}`}
            pointerEvents="none"
          />
        )}
        {m.scale.reference && tool !== "measure" && (
          <line
            x1={m.scale.reference.p1.x}
            y1={m.scale.reference.p1.y}
            x2={m.scale.reference.p2.x}
            y2={m.scale.reference.p2.y}
            stroke="#0f8a72"
            strokeWidth={2 * px}
            strokeDasharray={`${6 * px} ${4 * px}`}
            pointerEvents="none"
          />
        )}
        {rubberFrom && pointer && (
          <line
            data-testid="rubber-band"
            x1={rubberFrom.x}
            y1={rubberFrom.y}
            x2={pointer.x}
            y2={pointer.y}
            stroke="#e08a2c"
            strokeWidth={2 * px}
            strokeDasharray={`${5 * px} ${4 * px}`}
            pointerEvents="none"
          />
        )}
        {tool === "measure" && props.measure.length === 2 && (
          <line
            data-testid="measurement-line"
            x1={props.measure[0].x}
            y1={props.measure[0].y}
            x2={props.measure[1].x}
            y2={props.measure[1].y}
            stroke="#e08a2c"
            strokeWidth={3 * px}
            pointerEvents="none"
          />
        )}
        {tool === "measure" &&
          props.measure.map((p, i) => (
            <circle
              key={i}
              className="fe-handle fe-handle-measure"
              cx={p.x}
              cy={p.y}
              r={handleR}
              strokeWidth={2 * px}
              onPointerDown={(e) => startDrag(e, { kind: "measure", index: i })}
            />
          ))}
        {tool === "straighten" && props.corners.length > 0 && (
          <polyline
            points={props.corners.map((p) => `${p.x},${p.y}`).join(" ")}
            fill="none"
            stroke="#e08a2c"
            strokeWidth={3 * px}
          />
        )}
      </svg>
      {props.children?.({ toScreen })}
      {mpp && pointer && rubberFrom && (
        <div className="fe-readout">
          {(Math.hypot(pointer.x - rubberFrom.x, pointer.y - rubberFrom.y) * mpp).toFixed(2)} m
        </div>
      )}
      <div className="fe-zoom">
        <button aria-label="Zoom in" onClick={() => setBox((b) => ({ x: b.x + b.w * 0.1, y: b.y + b.h * 0.1, w: b.w * 0.8, h: b.h * 0.8 }))}>+</button>
        <button aria-label="Zoom out" onClick={() => setBox((b) => ({ x: b.x - b.w * 0.125, y: b.y - b.h * 0.125, w: b.w * 1.25, h: b.h * 1.25 }))}>−</button>
        <button aria-label="Fit to screen" onClick={fit}>Fit</button>
      </div>
    </div>
  );
}

function OpeningSymbol({ m, o, px, selected, onDown }: { m: PlanModel; o: Opening; px: number; selected: boolean; onDown: (e: React.PointerEvent) => void }) {
  if (o.status === "rejected") return null;
  const ends = openingEnds(m, o);
  if (!ends) return null;
  const [p, q] = ends;
  const host = m.walls.find((w) => w.id === o.hostWallId);
  const t = host?.thicknessPx || 8;
  const l = Math.hypot(q.x - p.x, q.y - p.y) || 1;
  const u = { x: (q.x - p.x) / l, y: (q.y - p.y) / l };
  const n = { x: -u.y, y: u.x };
  const side = o.swing === "right" ? -1 : 1;
  const proposed = o.status === "proposed";
  const hingeEnd = o.hinge === "end";
  const stroke = selected ? COLORS.selected : proposed ? "#d9480f" : o.kind === "window" ? COLORS.window : COLORS.wall;
  return (
    <g data-kind={o.kind} data-status={o.status} data-id={o.id} onPointerDown={onDown} className="fe-opening">
      {host && <line x1={p.x} y1={p.y} x2={q.x} y2={q.y} stroke="white" strokeWidth={t + 2 * px} />}
      {o.kind === "window" ? (
        <>
          {[-1, 1].map((k) => (
            <line
              key={k}
              x1={p.x + (n.x * t * k) / 4}
              y1={p.y + (n.y * t * k) / 4}
              x2={q.x + (n.x * t * k) / 4}
              y2={q.y + (n.y * t * k) / 4}
              stroke={stroke}
              strokeWidth={Math.max(1.5 * px, t / 6)}
            />
          ))}
        </>
      ) : o.kind === "garage" ? (
        <line x1={p.x} y1={p.y} x2={q.x} y2={q.y} stroke={stroke} strokeWidth={Math.max(2 * px, t / 3)} strokeDasharray={`${6 * px} ${4 * px}`} />
      ) : (
        <>
          <line
            x1={hingeEnd ? q.x : p.x}
            y1={hingeEnd ? q.y : p.y}
            x2={(hingeEnd ? q.x : p.x) + n.x * l * side}
            y2={(hingeEnd ? q.y : p.y) + n.y * l * side}
            stroke={stroke}
            strokeWidth={Math.max(1.5 * px, t / 5)}
          />
          <path
            d={`M ${(hingeEnd ? q.x : p.x) + n.x * l * side} ${(hingeEnd ? q.y : p.y) + n.y * l * side} A ${l} ${l} 0 0 ${(side > 0 ? 0 : 1) ^ (hingeEnd ? 1 : 0)} ${hingeEnd ? p.x : q.x} ${hingeEnd ? p.y : q.y}`}
            fill="none"
            stroke={stroke}
            strokeWidth={Math.max(1 * px, t / 8)}
            strokeDasharray={`${3 * px} ${2 * px}`}
          />
        </>
      )}
      {proposed && (
        <line x1={p.x} y1={p.y} x2={q.x} y2={q.y} stroke="#d9480f" strokeWidth={t + 6 * px} strokeOpacity={0.18} strokeLinecap="round" />
      )}
      <line x1={p.x} y1={p.y} x2={q.x} y2={q.y} stroke="transparent" strokeWidth={Math.max(t, 14 * px)} />
    </g>
  );
}
