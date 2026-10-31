"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { API, request, type Blueprint } from "../../lib/api";
import type { Finding, PlanModel, PlanResponse, Pt } from "../../lib/plan/model";
import { metersPerPixel, withDerived } from "../../lib/plan/derive";
import { deleteOpening, deleteWall, decideOpening, setReference } from "../../lib/plan/ops";
import PlanCanvas from "./PlanCanvas";
import Inspector from "./Inspector";
import ToolRail from "./ToolRail";
import TopBar, { type Display } from "./TopBar";
import MeasurePopover from "./MeasurePopover";
import type { Focus, Selection, Tool, ViewMode } from "./types";

const Plan3D = dynamic(() => import("./Plan3D"), { ssr: false });

export default function PlanEditor({ id }: { id: string }) {
  const [info, setInfo] = useState<Blueprint | null>(null);
  const [model, setModel] = useState<PlanModel | null>(null);
  const [past, setPast] = useState<PlanModel[]>([]);
  const [future, setFuture] = useState<PlanModel[]>([]);
  const [status, setStatus] = useState("Opening plan…");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [tool, setToolState] = useState<Tool>("select");
  const [selection, setSelection] = useState<Selection>(null);
  const [view, setView] = useState<ViewMode>("clean");
  const [display, setDisplay] = useState<Display>("2d");
  const [measure, setMeasure] = useState<Pt[]>([]);
  const [corners, setCorners] = useState<Pt[]>([]);
  const [aspect, setAspect] = useState("1.41421356");
  const [activeFinding, setActiveFinding] = useState<Finding | null>(null);
  const [fitNonce, setFitNonce] = useState(0);
  const [focus, setFocus] = useState<Focus>(null);
  const [outline, setOutline] = useState<Pt[] | null>(null);
  const [history, setHistory] = useState<{ revision: number; model: PlanModel }[]>([]);
  const revision = useRef(0);
  const saved = useRef("");
  const live = useRef<PlanModel | null>(null);
  const saving = useRef(false);
  const recoveryKey = "florp-plan-v2-" + id;
  const dirty = !!model && JSON.stringify(model) !== saved.current;

  const setTool = useCallback((t: Tool) => {
    setToolState(t);
    setMeasure([]);
    setCorners([]);
    if (t !== "select" && t !== "attach") setDisplay((d) => (d === "3d" ? "2d" : d));
  }, []);
  function adopt(r: PlanResponse) {
    revision.current = r.revision;
    saved.current = JSON.stringify(r.model);
    live.current = r.model;
    setModel(r.model);
  }
  function edit(next: PlanModel, record = true) {
    if (record && live.current) {
      const before = live.current;
      setPast((p) => [...p.slice(-49), before]);
      setFuture([]);
    }
    live.current = next;
    setModel(next);
    setStatus("Unsaved changes");
  }
  const checkpoint = () => {
    if (!live.current) return;
    const before = live.current;
    setPast((p) => [...p.slice(-49), before]);
    setFuture([]);
  };
  function undo() {
    if (!past.length || !model) return;
    const prev = past[past.length - 1];
    setFuture((f) => [model, ...f]);
    setPast((p) => p.slice(0, -1));
    live.current = prev;
    setModel(prev);
  }
  function redo() {
    if (!future.length || !model) return;
    const next = future[0];
    setPast((p) => [...p, model]);
    setFuture((f) => f.slice(1));
    live.current = next;
    setModel(next);
  }
  async function persist(next: PlanModel) {
    if (saving.current) return;
    saving.current = true;
    setStatus("Saving…");
    try {
      const r = await request<PlanResponse>(`/blueprints/${id}/plan`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expectedRevision: revision.current, model: next }),
      });
      revision.current = r.revision;
      if (live.current === next) {
        // Adopt the server's derived rooms/findings only if nothing changed meanwhile.
        adopt(r);
        setStatus("Saved");
        localStorage.removeItem(recoveryKey);
      } else {
        saved.current = JSON.stringify(r.model);
        setStatus("Unsaved changes");
      }
    } catch (e) {
      setError(String(e));
      setStatus("Save failed — edits kept on this device");
    } finally {
      saving.current = false;
    }
  }
  async function extract(expected: number, replacing: boolean, envelope?: Pt[]) {
    if (replacing && !envelope && !window.confirm("Replace the current plan with a fresh extraction? Saved revisions are kept in history.")) return;
    setBusy(true);
    setError("");
    setStatus("Finding walls, doors and windows…");
    try {
      const r = await request<PlanResponse>(`/blueprints/${id}/plan/extract?expected_revision=${expected}`, {
        method: "POST",
        ...(envelope ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ envelope }) } : {}),
      });
      adopt(r);
      setPast([]);
      setFuture([]);
      setSelection(null);
      setFitNonce((n) => n + 1);
      setStatus("Saved");
    } catch (e) {
      setError(String(e));
      setStatus("Extraction needs attention");
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    let active = true;
    Promise.all([request<PlanResponse>(`/blueprints/${id}/plan`), request<Blueprint>(`/blueprints/${id}/info`)])
      .then(([r, bp]) => {
        if (!active) return;
        setInfo(bp);
        revision.current = r.revision;
        const raw = localStorage.getItem(recoveryKey);
        if (r.model) {
          adopt(r);
          setStatus("Saved");
          if (raw) {
            try {
              const pending = JSON.parse(raw);
              if (pending.base === r.revision) {
                live.current = pending.model;
                setModel(pending.model);
                setStatus("Recovered unsaved changes");
              }
            } catch {}
          }
        } else void extract(0, false);
      })
      .catch((e) => active && setError(String(e)));
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);
  useEffect(() => {
    if (!model || !dirty) return;
    localStorage.setItem(recoveryKey, JSON.stringify({ base: revision.current, model }));
    if (error || busy) return;
    const t = setTimeout(() => live.current && void persist(live.current), 800);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [model, dirty, error, busy]);
  useEffect(() => {
    const leave = (e: BeforeUnloadEvent) => {
      if (live.current && JSON.stringify(live.current) !== saved.current) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", leave);
    return () => window.removeEventListener("beforeunload", leave);
  }, []);
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (el.closest("input,select,textarea")) return;
      const m = live.current;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        return e.shiftKey ? redo() : undo();
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === "escape") return setTool("select");
      const tools: Record<string, Tool> = { v: "select", m: "measure", w: "wall", d: "door", n: "window" };
      if (tools[k]) return setTool(tools[k]);
      if (k === "f") return setFitNonce((n) => n + 1);
      if (!m || !selection) return;
      if (k === "delete" || k === "backspace") {
        edit(selection.type === "wall" ? deleteWall(m, selection.id) : selection.type === "opening" ? deleteOpening(m, selection.id) : m);
        setSelection(null);
      }
      if (selection.type === "opening" && (k === "a" || k === "r")) {
        const next = decideOpening(m, selection.id, k === "a" ? "confirm" : "reject");
        if (next) edit(next);
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  });

  if (!model)
    return (
      <main className="fe-loading">
        {busy && <progress />}
        <p>{error || status}</p>
        {error && <button onClick={() => void extract(revision.current, false)}>Try again</button>}
      </main>
    );
  const m = model;
  const mpp = metersPerPixel(m);
  const proposals = m.openings.filter((o) => o.status === "proposed").length;
  const exportBlocker = !mpp
    ? "Set one measurement first."
    : proposals
      ? `Approve or reject ${proposals} proposed opening${proposals > 1 ? "s" : ""} first.`
      : dirty
        ? "Saving your latest changes…"
        : null;
  const select = (s: Selection, at?: Pt) => {
    setSelection(s);
    if (at) setFocus({ point: at, nonce: Date.now() });
  };
  const straightenPanel = (
    <section className="fe-card fe-accent">
      <h3>Straighten photographed sheet</h3>
      <p>Click the four paper corners: top-left, top-right, bottom-right, bottom-left.</p>
      <p>{corners.length} / 4 corners</p>
      <label>
        Page width / height
        <select aria-label="Page proportions" value={aspect} onChange={(e) => setAspect(e.target.value)}>
          <option value="1.41421356">A-series landscape</option>
          <option value="0.70710678">A-series portrait</option>
          <option value="1">Square</option>
        </select>
      </label>
      <label>
        Custom ratio
        <input aria-label="Custom page ratio" type="number" min=".1" max="10" step=".01" value={aspect} onChange={(e) => setAspect(e.target.value)} />
      </label>
      <p className="fe-muted">Creates a new plan and keeps the original.</p>
      <button
        className="fe-primary"
        disabled={corners.length !== 4 || dirty || !(Number(aspect) >= 0.1 && Number(aspect) <= 10)}
        onClick={async () => {
          setBusy(true);
          try {
            const r = await request<{ id: string }>(`/blueprints/${id}/plan/straighten`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ corners: corners.map((p) => [p.x, p.y]), pageAspectRatio: Number(aspect), expectedRevision: revision.current }),
            });
            window.location.href = "/plan/" + r.id;
          } catch (e) {
            setError(String(e));
            setBusy(false);
          }
        }}
      >
        Create straightened plan
      </button>
      <button onClick={() => setCorners([])}>Place corners again</button>
      <button onClick={() => setTool("select")}>Cancel</button>
    </section>
  );
  const historyPanel = (
    <details
      className="fe-history"
      onToggle={(e) => {
        if (e.currentTarget.open)
          void request<{ revision: number; model: PlanModel }[]>(`/blueprints/${id}/plan/history`).then(setHistory).catch((e) => setError(String(e)));
      }}
    >
      <summary>History & source notes</summary>
      {m.notes.map((n, i) => (
        <p key={i} className="fe-muted">{n}</p>
      ))}
      {history.map((h) => (
        <button key={h.revision} onClick={() => window.confirm(`Restore revision ${h.revision}? Later revisions are kept.`) && edit(withDerived(h.model))}>
          Restore revision {h.revision}
        </button>
      ))}
    </details>
  );
  const canvas = (
    <PlanCanvas
      model={m}
      imageUrl={`${API}/blueprints/${id}/preview`}
      view={view}
      tool={tool}
      setTool={setTool}
      selection={selection}
      select={(s) => {
        setSelection(s);
        setActiveFinding(null);
      }}
      activeFinding={activeFinding}
      measure={measure}
      setMeasure={setMeasure}
      corners={corners}
      setCorners={setCorners}
      edit={edit}
      checkpoint={checkpoint}
      fail={(msg) => setError(msg)}
      fitNonce={fitNonce}
      focus={focus}
      outline={outline}
      setOutline={setOutline}
      commitOutline={(o) => void extract(revision.current, true, o)}
    >
      {({ toScreen }) =>
        tool === "measure" && measure.length === 2 ? (
          <MeasurePopover
            points={measure}
            toScreen={toScreen}
            pixelsPerMeterNow={mpp ? 1 / mpp : null}
            apply={(meters) => {
              edit(setReference(m, measure[0], measure[1], meters));
              setTool("select");
            }}
            cancel={() => setMeasure([])}
          />
        ) : null
      }
    </PlanCanvas>
  );
  return (
    <div className="fe" data-display={display}>
      <TopBar
        title={info?.filename || "Floor plan"}
        status={status}
        dirty={dirty}
        onSave={() => live.current && void persist(live.current)}
        canUndo={past.length > 0}
        canRedo={future.length > 0}
        undo={undo}
        redo={redo}
        display={display}
        setDisplay={setDisplay}
        scaled={!!mpp}
        exportBlocker={exportBlocker}
        exportPlanHref={`${API}/blueprints/${id}/plan/export`}
        export3D={() => void import("../../lib/exportPlan3D").then((x) => x.exportPlan3D(m)).catch((e) => setError(String(e)))}
      />
      <ToolRail
        projectHref={info ? "/project/" + info.project_id : "/"}
        tool={tool}
        setTool={setTool}
        view={view}
        setView={setView}
        busy={busy}
        onStraighten={() => {
          setTool("straighten");
          setView("original");
          setDisplay("2d");
        }}
        onReextract={() => void extract(revision.current, true)}
      />
      <main className="fe-stage">
        {error && (
          <div className="fe-error" role="alert">
            <span>{error}</span>
            <button onClick={() => { setError(""); if (live.current && dirty) void persist(live.current); }}>Retry</button>
            <button
              onClick={() => {
                const a = document.createElement("a");
                a.href = URL.createObjectURL(new Blob([JSON.stringify(live.current)], { type: "application/json" }));
                a.download = "florp-recovery.json";
                a.click();
              }}
            >
              Download recovery
            </button>
            <button onClick={() => setError("")} aria-label="Dismiss">×</button>
          </div>
        )}
        {busy && <progress className="fe-progress" />}
        {display !== "3d" && canvas}
        {display !== "2d" && mpp && <Plan3D model={m} />}
      </main>
      <Inspector
        model={m}
        tool={tool}
        setTool={setTool}
        selection={selection}
        select={select}
        edit={edit}
        fail={setError}
        activeFinding={activeFinding}
        setActiveFinding={setActiveFinding}
        measureCount={measure.length}
        straighten={straightenPanel}
        history={historyPanel}
        outlinePanel={
          <section className="fe-section" data-testid="outline-panel">
            <label>
              <input
                type="checkbox"
                checked={!!outline}
                onChange={() => {
                  const w = m.imageTransform.width,
                    h = m.imageTransform.height;
                  setOutline(outline ? null : m.envelope ?? [{ x: w * 0.05, y: h * 0.05 }, { x: w * 0.95, y: h * 0.05 }, { x: w * 0.95, y: h * 0.95 }, { x: w * 0.05, y: h * 0.95 }]);
                }}
              />{" "}
              Building outline
            </label>
            {outline && <p className="fe-muted">Drag a corner to correct the outline; the plan is re-extracted inside it.</p>}
          </section>
        }
      />
    </div>
  );
}
