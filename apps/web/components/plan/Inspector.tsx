"use client";
import { useState } from "react";
import type { Finding, FindingCategory, PlanModel, Pt } from "../../lib/plan/model";
import { FINDING_LABELS } from "../../lib/plan/model";
import { areaM2, metersPerPixel, nodeMap, openingEnds, wallLength } from "../../lib/plan/derive";
import { decideOpening, deleteOpening, deleteWall, dismissFinding, patchOpening, patchWall, setRoomLabel } from "../../lib/plan/ops";
import type { Selection, Tool } from "./types";

type Props = {
  model: PlanModel;
  tool: Tool;
  setTool: (t: Tool) => void;
  selection: Selection;
  select: (s: Selection, focus?: Pt) => void;
  edit: (next: PlanModel) => void;
  fail: (m: string) => void;
  activeFinding: Finding | null;
  setActiveFinding: (f: Finding | null) => void;
  measureCount: number;
  straighten: React.ReactNode;
  history: React.ReactNode;
  outlinePanel?: React.ReactNode;
};

const fmt = (v: number | null, unit: string, digits = 2) => (v === null ? "—" : v.toFixed(digits) + " " + unit);

export default function Inspector(p: Props) {
  const m = p.model;
  const mpp = metersPerPixel(m);
  const len = (px: number) => (mpp ? fmt(px * mpp, "m") : px.toFixed(0) + " px");
  const proposals = m.openings.filter((o) => o.status === "proposed");
  const [cursor, setCursor] = useState(0);
  const groups = new Map<FindingCategory, Finding[]>();
  for (const f of m.findings) {
    if (f.category === "opening_needs_approval") continue;
    groups.set(f.category, [...(groups.get(f.category) || []), f]);
  }
  const nodes = nodeMap(m);
  const centreOf = (id: string): Pt | undefined => {
    const o = m.openings.find((x) => x.id === id);
    if (o) {
      const e = openingEnds(m, o, nodes);
      return e ? { x: (e[0].x + e[1].x) / 2, y: (e[0].y + e[1].y) / 2 } : undefined;
    }
    const w = m.walls.find((x) => x.id === id);
    if (w) {
      const a = nodes.get(w.a)!,
        b = nodes.get(w.b)!;
      return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    }
    return nodes.get(id);
  };
  function openFinding(f: Finding) {
    p.setActiveFinding(f);
    const target = f.targetIds[0];
    const isWall = m.walls.some((w) => w.id === target);
    const wallAtNode = m.walls.find((w) => w.a === target || w.b === target);
    p.select(
      isWall ? { type: "wall", id: target } : wallAtNode ? { type: "wall", id: wallAtNode.id } : null,
      f.anchor,
    );
  }
  function focusProposal(i: number) {
    const o = proposals[(i + proposals.length) % proposals.length];
    if (!o) return;
    setCursor((i + proposals.length) % proposals.length);
    p.select({ type: "opening", id: o.id }, centreOf(o.id));
  }
  function advance(done: string) {
    const rest = proposals.filter((o) => o.id !== done);
    const o = rest[Math.min(cursor, rest.length - 1)];
    if (o) p.select({ type: "opening", id: o.id }, centreOf(o.id));
    else p.select(null);
  }
  const current =
    (p.selection?.type === "opening" && proposals.find((o) => o.id === p.selection!.id)) ||
    proposals[Math.min(cursor, proposals.length - 1)];

  const selWall = p.selection?.type === "wall" ? m.walls.find((w) => w.id === p.selection!.id) : undefined;
  const selOpening = p.selection?.type === "opening" ? m.openings.find((o) => o.id === p.selection!.id) : undefined;
  const selRoom = p.selection?.type === "room" ? m.rooms.find((r) => r.id === p.selection!.id) : undefined;

  if (p.tool === "straighten") return <aside className="fe-inspector">{p.straighten}</aside>;
  return (
    <aside className="fe-inspector" aria-label="Inspector">
      {p.tool === "measure" && (
        <section className="fe-card fe-accent">
          <h3>Set one measurement</h3>
          <ol className="fe-steps">
            <li data-done={p.measureCount > 0}>Click the start of a dimension you know.</li>
            <li data-done={p.measureCount > 1}>Click its end (hold Shift to keep it straight).</li>
            <li>Enter the real length in the box on the drawing.</li>
          </ol>
        </section>
      )}
      {(p.tool === "wall" || p.tool === "door" || p.tool === "window") && (
        <section className="fe-card fe-accent">
          <h3>Add {p.tool}</h3>
          <p>
            Click two points{p.tool === "wall" ? ". Ends snap to nearby corners and walls." : " along a wall."} Hold Shift
            for a straight line. Esc cancels.
          </p>
        </section>
      )}
      {p.tool === "attach" && (
        <section className="fe-card fe-accent">
          <h3>Attach to a wall</h3>
          <p>Click the wall this opening belongs to.</p>
          <button onClick={() => p.setTool("select")}>Cancel</button>
        </section>
      )}

      {proposals.length > 0 && current && (
        <section className="fe-card fe-approval" data-testid="approval-queue">
          <header>
            <h3>Needs your approval ({proposals.length})</h3>
            <span className="fe-muted">{Math.round(current.confidence * 100)}% sure</span>
          </header>
          <p>
            {current.hostWallId
              ? `Is this a ${current.kind}? Compare it with the original drawing.`
              : `Possible ${current.kind} not on a wall. Attach it to a wall or reject it.`}
          </p>
          <div className="fe-row">
            <button
              className="fe-primary"
              disabled={!current.hostWallId}
              onClick={() => {
                const next = decideOpening(m, current.id, "confirm");
                if (next) {
                  p.edit(next);
                  advance(current.id);
                }
              }}
            >
              Approve {current.kind}
            </button>
            <button
              onClick={() => {
                p.edit(decideOpening(m, current.id, "reject")!);
                advance(current.id);
              }}
            >
              Reject
            </button>
          </div>
          <div className="fe-row">
            <button onClick={() => p.edit(patchOpening(m, current.id, current.kind === "door" ? { kind: "window", sillM: 0.9, heightM: 1.2 } : { kind: "door", sillM: 0, heightM: 2.1 }))}>
              It&apos;s a {current.kind === "door" ? "window" : "door"}
            </button>
            <button
              onClick={() => {
                p.select({ type: "opening", id: current.id }, centreOf(current.id));
                p.setTool("attach");
              }}
            >
              {current.hostWallId ? "Move to wall" : "Attach to wall"}
            </button>
          </div>
          <div className="fe-row fe-nav">
            <button aria-label="Previous proposal" onClick={() => focusProposal(cursor - 1)}>‹ Prev</button>
            <button aria-label="Next proposal" onClick={() => focusProposal(cursor + 1)}>Next ›</button>
          </div>
        </section>
      )}

      {selWall && (
        <section className="fe-card" data-testid="selection">
          <small className="fe-eyebrow">WALL</small>
          <h3>{len(wallLength(m, selWall, nodes))}</h3>
          <label>
            Thickness ({mpp ? "m" : "px"})
            <input
              type="number"
              min="0.01"
              step={mpp ? 0.01 : 1}
              value={Number((selWall.thicknessPx * (mpp || 1)).toFixed(3))}
              onChange={(e) => Number(e.target.value) > 0 && p.edit(patchWall(m, selWall.id, { thicknessPx: Number(e.target.value) / (mpp || 1) }))}
            />
          </label>
          <label>
            Height (m)
            <input type="number" min="0.5" max="20" step="0.1" value={selWall.heightM} onChange={(e) => Number(e.target.value) > 0 && p.edit(patchWall(m, selWall.id, { heightM: Number(e.target.value) }))} />
          </label>
          <label>
            Material
            <select value={selWall.material} onChange={(e) => p.edit(patchWall(m, selWall.id, { material: e.target.value as "block" | "concrete" }))}>
              <option value="block">Block</option>
              <option value="concrete">Concrete (safe room)</option>
            </select>
          </label>
          <p className="fe-muted">Drag the round handles to move corners; connected walls follow.</p>
          <button
            className="fe-danger"
            onClick={() => {
              p.edit(deleteWall(m, selWall.id));
              p.select(null);
            }}
          >
            Not a wall — delete
          </button>
        </section>
      )}
      {selOpening && (
        <section className="fe-card" data-testid="selection">
          <small className="fe-eyebrow">{selOpening.kind.toUpperCase()} · {selOpening.status}</small>
          <h3>{len(selOpening.widthPx)} wide</h3>
          <label>
            Height (m)
            <input type="number" min="0.3" step="0.05" value={selOpening.heightM} onChange={(e) => Number(e.target.value) > 0 && p.edit(patchOpening(m, selOpening.id, { heightM: Number(e.target.value) }))} />
          </label>
          {selOpening.kind === "window" && (
            <label>
              Sill height (m)
              <input type="number" min="0" step="0.05" value={selOpening.sillM} onChange={(e) => p.edit(patchOpening(m, selOpening.id, { sillM: Math.max(0, Number(e.target.value)) }))} />
            </label>
          )}
          {selOpening.kind === "door" && (
            <>
              <button onClick={() => p.edit(patchOpening(m, selOpening.id, { swing: selOpening.swing === "right" ? "left" : "right" }))}>Flip swing</button>
              <button onClick={() => p.edit(patchOpening(m, selOpening.id, { hinge: selOpening.hinge === "end" ? "start" : "end" }))}>Flip hinge</button>
            </>
          )}
          <p className="fe-muted">Drag the middle handle to slide it along the wall, the square handles to resize.</p>
          <button
            className="fe-danger"
            onClick={() => {
              p.edit(deleteOpening(m, selOpening.id));
              p.select(null);
            }}
          >
            Delete {selOpening.kind}
          </button>
        </section>
      )}
      {selRoom && (
        <section className="fe-card" data-testid="selection">
          <small className="fe-eyebrow">ROOM</small>
          <h3 data-testid="room-area">{mpp ? fmt(areaM2(m, selRoom.areaPx2), "m²") : "Set a measurement to see area"}</h3>
          <label>
            Name
            <input placeholder="e.g. Bedroom" value={selRoom.label || ""} onChange={(e) => p.edit(setRoomLabel(m, selRoom.id, e.target.value))} />
          </label>
          <p className="fe-muted">Usable floor area, measured to the inner wall faces.</p>
        </section>
      )}

      {groups.size > 0 && (
        <section className="fe-card" aria-label="Findings">
          <h3>Review</h3>
          {[...groups].map(([category, items]) => (
            <details key={category} className="fe-group" data-category={category}>
              <summary>
                {FINDING_LABELS[category]} ({items.reduce((s, f) => s + f.count, 0)})
              </summary>
              <ul>
                {items.map((f) => (
                  <li
                    key={f.id}
                    className={p.activeFinding?.id === f.id ? "active" : ""}
                    onMouseEnter={() => p.setActiveFinding(f)}
                    onMouseLeave={() => p.activeFinding?.id === f.id && p.setActiveFinding(null)}
                  >
                    <button className="fe-link" onClick={() => openFinding(f)}>{f.message}</button>
                    {f.severity === "warn" && (
                      <button
                        className="fe-dismiss"
                        aria-label="Dismiss finding"
                        onClick={() => {
                          p.edit(dismissFinding(m, f.id));
                          p.setActiveFinding(null);
                        }}
                      >
                        ×
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </details>
          ))}
        </section>
      )}

      <section className="fe-card" aria-label="Plan summary">
        <h3>Plan</h3>
        <p className="fe-stats">
          <span>{m.walls.length} walls</span>
          <span>{m.openings.filter((o) => o.status !== "rejected").length} openings</span>
          <span data-testid="room-count">{m.rooms.length} rooms</span>
        </p>
        {!mpp && (
          <button className="fe-primary" onClick={() => p.setTool("measure")}>
            Set one measurement
          </button>
        )}
        {m.rooms.length > 0 && (
          <ul className="fe-rooms">
            {m.rooms.map((r, i) => (
              <li key={r.id}>
                <button className="fe-link" onClick={() => p.select({ type: "room", id: r.id })}>
                  {r.label || `Room ${i + 1}`}
                </button>
                <span data-testid="room-row-area">{mpp ? fmt(areaM2(m, r.areaPx2), "m²", 1) : "—"}</span>
              </li>
            ))}
          </ul>
        )}
        {p.outlinePanel}
      {p.history}
      </section>
    </aside>
  );
}
