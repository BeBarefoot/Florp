"use client";

import { useEffect, useState } from "react";
import { nodeMap, openingEnds } from "../../lib/plan/derive";
import type { PlanModel, Pt } from "../../lib/plan/model";
import { addWall, decideOpening, dismissFinding, patchOpening } from "../../lib/plan/ops";

export default function GuidedReview({ model, imageUrl, edit, addDoor, attachOpening, next, close }: {
  model: PlanModel;
  imageUrl: string;
  edit: (model: PlanModel) => void;
  addDoor: () => void;
  attachOpening: (id: string) => void;
  next: () => void;
  close: () => void;
}) {
  const [skipped, setSkipped] = useState<string[]>([]);
  const nodes = nodeMap(model);
  const candidates = model.openings.flatMap(opening => {
    if (opening.status !== "proposed") return [];
    const span = openingEnds(model, opening, nodes);
    return span ? [{ id: opening.id, span, opening, closure: null }] : [];
  });
  const closures = model.findings.flatMap(finding => finding.closure && !model.dismissedFindings.includes(finding.id)
    ? [{ id: finding.id, span: [finding.closure.start, finding.closure.end], opening: null, closure: finding.closure }]
    : []);
  const candidate = [...candidates, ...closures].find(item => !skipped.includes(item.id));
  useEffect(() => {
    function dismiss(event: KeyboardEvent) {
      if (event.key === "Escape") close();
    }
    window.addEventListener("keydown", dismiss);
    return () => window.removeEventListener("keydown", dismiss);
  }, [close]);

  if (!candidate) return <section className="guided-review" aria-label="Guided review">
    <header><h2>Review the plan</h2><button onClick={close}>Done</button></header>
    <p>{skipped.length ? "Skipped findings are still open." : "No suggested openings or wall closures to review."}</p>
    {skipped.length > 0 && <button onClick={() => setSkipped([])}>Review skipped findings</button>}
    <div className="guided-actions"><button className="fe-primary" onClick={next}>Continue to scale</button>
      <button onClick={addDoor}>Mark a missing door</button></div>
  </section>;

  const [a, b] = candidate.span;
  const size = Math.max(60, Math.hypot(b.x - a.x, b.y - a.y) * 2.5);
  const box = `${(a.x + b.x - size) / 2} ${(a.y + b.y - size * .65) / 2} ${size} ${size * .65}`;
  function line(p: Pt, q: Pt, color: string, width: number, key?: string, dash?: string) {
    return <line key={key} x1={p.x} y1={p.y} x2={q.x} y2={q.y} stroke={color} strokeWidth={width} strokeDasharray={dash}/>;
  }
  const span = line(a, b, "#a7452d", size * .017, undefined, `${size * .035} ${size * .015}`);
  const opening = candidate.opening;
  function confirm(passage: boolean) {
    if (!opening) return;
    const next = passage ? patchOpening(model, opening.id, { swing: null, passage: true }) : model;
    const result = decideOpening(next, opening.id, "confirm");
    if (result) edit(result);
  }
  return <section className="guided-review" aria-label="Guided review">
    <header><h2>{opening ? `Check this ${opening.kind === "garage" ? "garage opening" : opening.kind}` : "Check this wall gap"}</h2>
      <button onClick={close}>Close review</button></header>
    <div className="guided-comparison">
      <figure><figcaption>Original drawing</figcaption><svg viewBox={box} role="img" aria-label="Selected span on the original drawing">
        <image href={imageUrl} width={model.imageTransform.width} height={model.imageTransform.height}/>
        {span}
      </svg></figure>
      <figure><figcaption>Plan model</figcaption><svg viewBox={box} role="img" aria-label="Same span in the plan model">
        {model.walls.map(wall => {
          const start = nodes.get(wall.a), end = nodes.get(wall.b);
          return start && end ? line(start, end, "#34473b", wall.thicknessPx, wall.id) : null;
        })}
        {model.openings.flatMap(other => {
          if (other.status !== "confirmed") return [];
          const ends = openingEnds(model, other, nodes);
          const wall = model.walls.find(w => w.id === other.hostWallId);
          return ends ? [line(...ends, "#dbe5df", wall?.thicknessPx ?? size * .035, other.id)] : [];
        })}
        {span}
      </svg></figure>
    </div>
    <div className="guided-actions">
      {opening ? <>
        <button className="fe-primary" disabled={!opening.hostWallId} onClick={() => confirm(false)}>
          {opening.kind === "door" ? "Door" : opening.kind === "window" ? "Window" : "Garage opening"}
        </button>
        {opening.kind === "door" && <button disabled={!opening.hostWallId} onClick={() => confirm(true)}>Open passage</button>}
        {!opening.hostWallId && <button onClick={() => attachOpening(opening.id)}>Attach to a wall</button>}
        <button onClick={() => {
          const result = decideOpening(model, opening.id, "reject");
          if (result) edit(result);
        }}>{opening.hostWallId ? "Solid wall" : "Reject opening"}</button>
      </> : <button className="fe-primary" onClick={() => {
        const closure = candidate.closure;
        if (!closure) return;
        const result = addWall(model, closure.start, closure.end, closure.thicknessPx, 1e-7);
        if (result.wallId) edit(dismissFinding(result.model, candidate.id));
      }}>Add closing wall</button>}
      <button onClick={() => setSkipped(current => [...current, candidate.id])}>Skip</button>
      <button onClick={addDoor}>Mark a missing door</button>
    </div>
  </section>;
}
