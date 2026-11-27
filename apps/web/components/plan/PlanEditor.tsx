"use client";
import {ExtractionProgress} from "./ExtractionProgress";
import {extractWithProgress, type ExtractionProgress as ExtractionState} from "../../lib/plan/extractionProgress";
import { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { BrickWall, DoorOpen, MousePointer2, PanelTop, Trash2, Undo2 } from "lucide-react";
import { API, request, type Blueprint } from "../../lib/api";
import type { Finding, PlanModel, PlanResponse, Pt } from "../../lib/plan/model";
import { metersPerPixel, scaleCheck, wallFootprint, withDerived } from "../../lib/plan/derive";
import { StairFields, WindowFields } from "./OpeningAndStairFields";
import { deleteOpening, deleteWall, decideOpening, patchOpening, setReference } from "../../lib/plan/ops";
import {regionArea} from "../SiteOutline";
import PlanCanvas from "./PlanCanvas";
import Inspector from "./Inspector";
import GuidedReview from "./GuidedReview";
import PlanReview, {type ReviewState} from "./PlanReview";
import ToolRail from "./ToolRail";
import TopBar, { type Display } from "./TopBar";
import MeasurePopover from "./MeasurePopover";
import type { Focus, Selection, Tool, ViewMode } from "./types";
import type { Saved } from "../../lib/plan/scene";

const Plan3D = dynamic(() => import("./Plan3D"), { ssr: false });

export default function PlanEditor({ id, phone=false }: { id: string; phone?: boolean }) {
  const router = useRouter();
  const [guided, setGuided] = useState(false);
  const reviewButton = useRef<HTMLButtonElement>(null);
  const closeGuided = useCallback(() => {
    setGuided(false);
    reviewButton.current?.focus();
  }, []);
  const [showSite,setShowSite]=useState(true);
  const [info, setInfo] = useState<Blueprint | null>(null);
  const [model, setModel] = useState<PlanModel | null>(null);
  const [past, setPast] = useState<PlanModel[]>([]);
  const [future, setFuture] = useState<PlanModel[]>([]);
  const [latestExtractor, setLatestExtractor] = useState(0);
  const [status, setStatus] = useState("Opening plan…");
  const [error, setError] = useState("");
  const [extraction, setExtraction] = useState<ExtractionState | null>(null);
  const [busy, setBusy] = useState(false);
  const [tool, setToolState] = useState<Tool>("select");
  const [selection, setSelection] = useState<Selection>(null);
  const [view, setView] = useState<ViewMode>(phone?"overlay":"clean");
  const [display, setDisplay] = useState<Display>("2d");
  const [measure, setMeasure] = useState<Pt[]>([]);
  const [checkingScale,setCheckingScale]=useState(false);
  const [reviewingScale,setReviewingScale]=useState(false);
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
  const saveDone = useRef<Promise<void> | null>(null);
  const recoveryKey = "florp-plan-v2-" + id;
  const dirty = !!model && JSON.stringify(model) !== saved.current;

  const setTool = useCallback((t: Tool) => {
    setToolState(t);
    setCheckingScale(false);
    setMeasure([]);
    setCorners([]);
    if (t !== "select" && t !== "attach") setDisplay((d) => (d === "3d" ? "2d" : d));
  }, []);
  const calibrated = !!model && !!metersPerPixel(model);
  const loaded = !!model;
  useEffect(() => {
    if (!loaded) return;
    const params = new URLSearchParams(window.location.search);
    if (!phone && params.has("review")) setGuided(true);
    const openingId = params.get("opening");
    if (openingId && live.current?.openings.some(opening=>opening.id===openingId)) {
      setSelection({type:"opening",id:openingId});
      return;
    }
    const setup = params.get("setup");
    if (setup !== "floor" && setup !== "finishes" && setup !== "furniture") return;
    if (calibrated) setDisplay("3d");
    else {
      setView("original");
      setTool("measure");
    }
  }, [loaded, calibrated, phone, setTool]);
  function adopt(r: PlanResponse) {
    if (r.latestExtractionVersion) setLatestExtractor(r.latestExtractionVersion);
    revision.current = r.revision;
    saved.current = JSON.stringify(r.model);
    live.current = r.model;
    setModel(r.model);
  }
  function edit(next: PlanModel, record = true) {
    const current = live.current;
    if (current && next.findings === current.findings && next.findings.some(f=>f.closure) &&
        (next.nodes !== current.nodes || next.walls !== current.walls || next.openings !== current.openings)) {
      // Source evidence refers to a particular wall graph. Align walls can
      // search the edited floor again, and undo restores the earlier findings.
      next = {...next, findings: next.findings.filter(f=>!f.closure)};
      setActiveFinding(null);
    }
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
    if (saving.current) return false;
    saving.current = true;
    let finish!: () => void;
    saveDone.current = new Promise<void>((resolve) => { finish = resolve; });
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
        return true;
      } else {
        saved.current = JSON.stringify(r.model);
        setStatus("Unsaved changes");
        return false;
      }
    } catch (e) {
      setError(String(e));
      setStatus("Save failed — edits kept on this device");
      return false;
    } finally {
      saving.current = false;
      finish();
      saveDone.current = null;
    }
  }
  async function restoreBundle(file: File) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      if (saveDone.current) await saveDone.current;
      const current = live.current;
      const form = new FormData();
      form.append("file", file);
      const restored = await request<PlanModel>(`/blueprints/${id}/plan/restore-bundle`, {method:"POST", body:form});
      if (live.current !== current || restored.revision !== revision.current)
        throw Error("The floor changed while reading the bundle. Reload or try again.");
      edit(restored);
      setSelection(null);
      setActiveFinding(null);
      setTool("select");
      setStatus("Corrected plan loaded");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function alignWalls() {
    if (busy) return;
    setBusy(true);
    setError("");
    setStatus("Checking wall connections…");
    try {
      if (saveDone.current) await saveDone.current;
      const current = live.current;
      if (!current) return;
      const next = await request<PlanModel>(`/blueprints/${id}/plan/align-walls?recover_missing=true`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expectedRevision: revision.current, model: current }),
      });
      if (live.current !== current) {
        setError("The plan changed during alignment. Try Align walls again.");
        return;
      }
      if (JSON.stringify(next) !== JSON.stringify(current)) edit(next);
      else setStatus(JSON.stringify(current) === saved.current ? "Saved" : "Unsaved changes");
      setActiveFinding(null);
      return next;
    } catch (e) {
      setError(String(e));
      setStatus("Wall connection check failed");
    } finally {
      setBusy(false);
    }
  }
  async function detectYard() {
    if (busy) return;
    setBusy(true);
    try {
      const gardens=await request<NonNullable<PlanModel["gardens"]>>(`/blueprints/${id}/plan/yard`);
      if (!live.current || live.current.id!==id) return;
      if (!gardens.length) { setStatus("No shaded yard found on the source drawing"); return; }
      edit({...live.current,gardens});
      setShowSite(true);
      setStatus(gardens.some(region=>region.surface==="paving")?"Lawn and patio detected":"Yard detected");
    } catch (e) { setError(String(e)); }
    finally { setBusy(false); }
  }
  async function detectStairs() {
    if (busy) return;
    setBusy(true);
    setError("");
    setStatus("Looking for stairs…");
    try {
      if (saveDone.current) await saveDone.current;
      const current = live.current;
      if (!current) return;
      const next = await request<PlanModel>(`/blueprints/${id}/plan/detect-stairs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expectedRevision: revision.current, model: current }),
      });
      if (live.current !== current) {
        setError("The plan changed during stair detection. Try again.");
        return;
      }
      if (next.stairs?.length) {
        edit(next);
        select({ type: "stair", id: next.stairs[0].id });
      } else setStatus("No turning stairs found");
    } catch (e) {
      setError(String(e));
      setStatus("Stair detection failed");
    } finally {
      setBusy(false);
    }
  }
  async function commitOutline(envelope: Pt[]) {
    setBusy(true);
    // A corrected outline triggers extraction. Preserve pending manual edits
    // as a server revision before replacing the displayed geometry.
    if (saveDone.current) await saveDone.current;
    const current = live.current;
    if (current && JSON.stringify(current) !== saved.current && !(await persist(current))) {
      setBusy(false);
      return;
    }
    await extract(revision.current, true, envelope);
  }
  async function extract(expected: number, replacing: boolean, envelope?: Pt[]) {
    if (replacing && !envelope && !window.confirm("Replace the current plan with a fresh extraction? Saved revisions are kept in history.")) return;
    setBusy(true);
    setError("");
    try {
      if (replacing) {
        if (saveDone.current) await saveDone.current;
        const current = live.current;
        if (current && JSON.stringify(current) !== saved.current && !await persist(current)) return;
        expected = revision.current;
      }
      setStatus("Finding walls, doors and windows…");
      const r = await extractWithProgress(`/blueprints/${id}`, expected, setExtraction, envelope);
      adopt(r);
      setPast([]);
      setFuture([]);
      setSelection(null);
      setFitNonce((n) => n + 1);
      if (r.model) {
        const {walls, openings, roomSymbols} = r.model;
        setStatus(`Extracted · ${walls.length} wall segments · ${openings.length} openings · ${roomSymbols?.length ?? 0} objects`);
      }
    } catch (e) {
      setError(String(e));
      setStatus("Extraction needs attention");
    } finally {
      setExtraction(null);
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
        edit(selection.type === "wall" ? deleteWall(m, selection.id) : selection.type === "opening" ? deleteOpening(m, selection.id)
          : selection.type === "stair" ? { ...m, stairs: m.stairs?.filter((s) => s.id !== selection.id) } : m);
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
        {extraction && <ExtractionProgress state={extraction}/>}
        <p>{error || status}</p>
        {error && <button onClick={() => void extract(revision.current, false)}>Try again</button>}
      </main>
    );
  const m = model;
  const mpp = metersPerPixel(m);
  const check=scaleCheck(m);
  const checkText=check?`${(check.difference*100).toFixed(1)}% difference · ${check.expected.toFixed(2)} m on the model, ${check.measured.toFixed(2)} m measured.`:"Add a second known distance before relying on furniture fit.";
  function startScaleCheck(){
    setDisplay("2d");
    setView("overlay");
    setTool("measure");
    setCheckingScale(true);
  }
  function measureScale(){
    setReviewingScale(false);
    setDisplay("2d");
    setView("overlay");
    setTool("measure");
    setCheckingScale(false);
  }
  const scaleProposal = !mpp ? m.scale.proposal : undefined;
  const showScaleProposal = !!scaleProposal && reviewingScale && view === "overlay" && display === "2d" && tool === "select";
  const proposedScaleCheck = showScaleProposal && scaleProposal && scaleCheck({
    ...m,
    scale: { ...m.scale, reference: scaleProposal.reference, checkReference: scaleProposal.checkReference },
  });
  const scaleProposalButton = scaleProposal && (showScaleProposal ?
    <button disabled={busy} onClick={()=>{
      const {reference,checkReference}=scaleProposal;
      const next=setReference(m,reference.p1,reference.p2,reference.lengthMeters);
      edit({...next,scale:{...next.scale,checkReference}});
      setReviewingScale(false);
    }}>Use these measurements</button> :
    <button disabled={busy} onClick={()=>{
      setDisplay("2d");
      setView("overlay");
      setTool("select");
      setReviewingScale(true);
    }}>Review detected scale</button>);
  const scaleProposalText = scaleProposal && (showScaleProposal ?
    `Blue ${scaleProposal.reference.lengthMeters.toFixed(2)} m · Purple ${scaleProposal.checkReference.lengthMeters.toFixed(2)} m. Check both spans on the drawing.${proposedScaleCheck ? ` · ${(proposedScaleCheck.difference * 100).toFixed(1)}% apart` : ""}` :
    `Found ${scaleProposal.evidenceCount} agreeing printed dimensions. Review the scale before using it.`);
  const footprint = wallFootprint(m, mpp);
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
      <label>Restore corrected plan (.zip)
        <input type="file" accept=".zip,application/zip" disabled={busy} onChange={(e) => {
          const file = e.currentTarget.files?.[0];
          e.currentTarget.value = "";
          if (file) void restoreBundle(file);
        }} />
      </label>
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
      siteRegions={showSite?[...(m.gardens??[]),...(info?.floor?.regions??[]).filter(r=>r.kind!=="garden"||!m.gardens?.length)]:undefined}
      imageUrl={`${API}/blueprints/${id}/preview`}
      view={view}
      tool={tool}
      setTool={setTool}
      selection={selection}
      showScaleProposal={showScaleProposal}
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
      commitOutline={(o) => void commitOutline(o)}
    >
      {({ toScreen }) =>
        tool === "measure" && measure.length === 2 ? (
          <MeasurePopover
            model={m}
            points={measure}
            toScreen={toScreen}
            pixelsPerMeterNow={mpp ? 1 / mpp : null}
            checking={checkingScale}
            apply={(meters) => {
              edit(checkingScale?{...m,scale:{...m.scale,checkReference:{p1:measure[0],p2:measure[1],lengthMeters:meters}}}:
                setReference(m, measure[0], measure[1], meters));
              setTool("select");
            }}
            cancel={() => setMeasure([])}
          />
        ) : null
      }
    </PlanCanvas>
  );
  async function navigateAfterSave(destination: string) {
    if (saveDone.current) await saveDone.current;
    const current = live.current;
    if (!current || (JSON.stringify(current) !== saved.current && !await persist(current))) return;
    router.push(destination);
  }
  const openTour=()=>navigateAfterSave("/phone/showcase/" + encodeURIComponent(id) + "?from=editor");
  const olderExtraction = (m.extractionVersion ?? 0) < latestExtractor;
  const extractButton = <button disabled={busy} onClick={() => void extract(revision.current, true)}>
    {olderExtraction ? "Run latest extraction" : "Re-extract from drawing"}
  </button>;
  if(phone){
    const selectedWall=selection?.type==="wall"&&m.walls.find(w=>w.id===selection.id);
    const selectedOpening=selection?.type==="opening"?m.openings.find(o=>o.id===selection.id):undefined;
    const selectedStair=selection?.type==="stair"?m.stairs?.find(stair=>stair.id===selection.id):undefined;
    const selectedName=selectedStair?"Stair":selectedWall?"Wall":selectedOpening?.kind==="door"?"Door":selectedOpening?.kind==="window"?"Window":null;
    return <div className="fe phone-plan-editor" data-display="2d">
      <div className="phone-plan-header">
        <h1>Edit floor</h1>
        <button disabled={busy} onClick={()=>void openTour()}>Done</button>
      </div>
      <main className="fe-stage">{extraction && <ExtractionProgress state={extraction}/>} {canvas}</main>
      <div className="phone-plan-tools">
        <p role="status">{error||(tool==="select"?(selectedName?`${selectedName} selected`:"Tap a wall, door, window or stair.") :
          tool==="measure"?(checkingScale?"Tap both ends of a second known distance.":"Tap both ends of a known distance."):tool==="wall"?"Tap both ends of the wall.":"Tap both ends of the opening along a wall.")}</p>
        {error&&dirty&&<button onClick={()=>live.current&&void persist(live.current)}>Retry save</button>}
        <div className="phone-plan-actions" role="group" aria-label="Plan tools">
          {([["select","Select",MousePointer2],["wall","Wall",BrickWall],["door","Door",DoorOpen],["window","Window",PanelTop]] as const)
            .map(([value,label,Icon])=><button key={value} aria-pressed={tool===value}
              onClick={()=>{setError("");setSelection(null);setTool(tool===value?"select":value);}}><Icon size={18}/>{label}</button>)}
          <button disabled={!past.length} onClick={()=>{undo();setTool("select");setSelection(null);setError("");}}><Undo2 size={18}/>Undo</button>
          {selectedOpening?.status==="proposed"&&<button onClick={()=>{
            const next=decideOpening(m,selectedOpening.id,"confirm");
            if(next)edit(next);
          }}>Confirm {selectedName?.toLowerCase()}</button>}
          {selectedName&&<button onClick={()=>{
            if(selectedWall)edit(deleteWall(m,selectedWall.id));
            if(selectedOpening)edit(deleteOpening(m,selectedOpening.id));
            if(selectedStair)edit({...m,stairs:m.stairs?.filter(stair=>stair.id!==selectedStair.id)});
            setSelection(null);setTool("select");setError("");
          }}><Trash2 size={18}/>Remove {selectedName.toLowerCase()}</button>}
        </div>
        {selectedOpening?.kind==="window"&&<details key={selectedOpening.id} className="phone-plan-properties" open>
          <summary>Window dimensions and frame</summary>
          <WindowFields model={m} opening={selectedOpening} onPatch={patch=>edit(patchOpening(m,selectedOpening.id,patch))}/>
        </details>}
        {selectedStair&&<details key={selectedStair.id} className="phone-plan-properties">
          <summary>Stair direction and rise</summary>
          <StairFields stair={selectedStair} onPatch={patch=>edit({...m,stairs:m.stairs?.map(stair=>
            stair.id===selectedStair.id?{...stair,...patch}:stair)})}/>
        </details>}
        <div className="phone-plan-footer">
          {extractButton}
          <button aria-pressed={view==="overlay"} onClick={()=>setView(view==="overlay"?"clean":"overlay")}>Original drawing</button>
          <button onClick={()=>void navigateAfterSave("/plan/"+encodeURIComponent(id))}>Full editor</button>
          {mpp?<button onClick={startScaleCheck}>Check scale</button>:<button onClick={measureScale}>Measure scale</button>}
          {scaleProposalButton}
          <span>{dirty?"Unsaved changes":status}</span>
        </div>
        {scaleProposalText&&<p>{scaleProposalText}</p>}
        {mpp&&check&&<p role={check.mismatch?"alert":undefined}>{check.mismatch?"Measurements disagree. ":""}{checkText}</p>}
      </div>
    </div>;
  }
  return (
    <div className="fe desktop-plan" data-display={display}>
      <TopBar
        title={info?.filename || "Floor plan"}
        status={status}
        extractionAction={olderExtraction ? extractButton : null}
        dirty={dirty}
        onSave={() => live.current && void persist(live.current)}
        canUndo={past.length > 0}
        canRedo={future.length > 0}
        undo={undo}
        redo={redo}
        display={display}
        setDisplay={setDisplay}
        scaled={!!mpp}
        walkthroughBusy={busy}
        onWalkthrough={() => void navigateAfterSave("/studio/" + encodeURIComponent(id))}
        onPhoneWalkthrough={() => void openTour()}
        onOverview={() => void navigateAfterSave("/studio/" + encodeURIComponent(id) + "#overview")}
        reviewAction={<button ref={reviewButton} aria-pressed={guided} onClick={() => {
          setDisplay("2d");
          setGuided(open => !open);
        }}>Review plan{proposals > 0 ? ` (${proposals})` : ""}</button>}
        exportBlocker={exportBlocker}
        debugHref={`${API}/blueprints/${encodeURIComponent(id)}/plan/debug`}
        exportPlanHref={`${API}/blueprints/${id}/plan/export`}
        export3D={() => void (async () => {
          const snapshot = await request<PlanResponse>(`/blueprints/${id}/plan`);
          if (!snapshot.model || snapshot.revision !== revision.current || dirty)
            throw Error("Save or reload the current plan before exporting.");
          const [review, scene] = await Promise.all([
            request<ReviewState>(`/blueprints/${id}/plan/review?revision=${snapshot.revision}`),
            request<Saved>(`/blueprints/${id}/scene`),
          ]);
          const { exportPlan3D } = await import("../../lib/exportPlan3D");
          await exportPlan3D(snapshot.model, review, scene.revision?scene.config:undefined);
        })().catch((e) => setError(String(e)))}
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
        onAlignWalls={() => void alignWalls()}
        onReextract={() => void extract(revision.current, true)}
      />
      <main className="fe-stage">
        {extraction && <ExtractionProgress state={extraction}/>}
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
        {guided && display === "2d" && <GuidedReview model={m} imageUrl={`${API}/blueprints/${id}/preview`}
          edit={edit} close={closeGuided} attachOpening={openingId => {
            setGuided(false);
            setView("overlay");
            setSelection({type:"opening",id:openingId});
            setTool("attach");
          }} next={() => {
            closeGuided();
            if (mpp) startScaleCheck();
            else if (scaleProposal) {
              setView("overlay");
              setTool("select");
              setReviewingScale(true);
            } else measureScale();
          }} addDoor={() => {
            setGuided(false);
            setView("overlay");
            setTool("door");
          }}/>}
        {display !== "2d" && mpp && <Plan3D key={m.id} model={m} dirty={dirty} onPlanEdit={edit}
          savePlan={async () => live.current && await persist(live.current) ? live.current : null} />}
      </main>
      <Inspector
        reviewPanel={<>{scaleProposal&&<section className="fe-card fe-accent">
          <h3>Detected scale</h3>
          <p>{scaleProposalText}</p>
          {scaleProposalButton}
          <button onClick={measureScale}>Measure a known distance</button>
          <button disabled={busy} onClick={() => void navigateAfterSave("/studio/" + encodeURIComponent(id))}>Walk at approximate scale</button>
        </section>}{mpp&&<section className="fe-card">
          <h3>Scale check</h3>
          <p role={check?.mismatch?"alert":undefined}>{check?.mismatch?"Measurements disagree. Review the scale before checking furniture fit. ":""}{checkText}</p>
          <button onClick={startScaleCheck}>{check?"Measure again":"Check a second distance"}</button>
        </section>}{footprint?.unusuallySmall && <section className="fe-card fe-accent">
          <h3>Check the plan scale</h3>
          <p>The building spans {footprint.width.toFixed(2)} × {footprint.depth.toFixed(2)} m. Its walls are taller than either distance.</p>
          <button onClick={() => { setDisplay("2d"); setMeasure([]); setTool("measure"); }}>Measure a known distance</button>
        </section>}<button disabled={busy} onClick={()=>void detectYard()}>Detect yard</button>{info?.floor&&<section className="fe-section">
          <h3>{info.floor.level===1?"First floor":"Second floor"}</h3>
          <label><input type="checkbox" checked={showSite} onChange={e=>setShowSite(e.target.checked)}/> Garden and stair outlines</label>
          {info.floor.regions.filter(r=>r.kind==="garden").map((r,i)=><p key={i}>{r.surface==="paving"?"Patio":"Lawn"} · {mpp?
            regionArea(r,info.width,info.height,mpp).toFixed(1)+" m²":"Set a known distance to estimate area"}</p>)}
          <a href={"/plan/"+info.floor.otherId} target="_blank" rel="noopener noreferrer">Open {info.floor.level===1?"second":"first"} floor in a new tab</a>
        </section>}<PlanReview id={id} revision={m.revision} dirty={dirty}/></>}
        model={m}
        onDetectStairs={() => void detectStairs()}
        busy={busy}
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
