"use client";
import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import dynamic from "next/dynamic";
import { API, request, Pt, Blueprint } from "../../../lib/api";
import {
  Workspace,
  PlanDoc,
  Object2D,
  ppm,
  length,
  geometry,
  moveEndpoint,
  attach,
} from "../../../lib/planWorkspace";
const Viewer = dynamic(() => import("../../../components/Viewer3D"), {
  ssr: false,
});
const clone = <T,>(v: T): T => structuredClone(v);
export default function PlanWorkspace() {
  const { id } = useParams<{ id: string }>();
  const [bp, setBp] = useState<Blueprint | null>(null);
  const [state, setState] = useState<Workspace | null>(null);
  const [doc, setDoc] = useState<PlanDoc | null>(null);
  const [status, setStatus] = useState("Opening plan…");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState("");
  const [tool, setTool] = useState<
    "select" | "measure" | "wall" | "door" | "window" | "host"
  >("select");
  const [view, setView] = useState<"clean" | "overlay" | "original">("clean");
  const [three, setThree] = useState(false);
  const [points, setPoints] = useState<Pt[]>([]);
  const [pointer, setPointer] = useState<Pt | null>(null);
  const [distance, setDistance] = useState("");
  const [unit, setUnit] = useState("m");
  const [zoom, setZoom] = useState(1);
  const [past, setPast] = useState<PlanDoc[]>([]);
  const [future, setFuture] = useState<PlanDoc[]>([]);
  const [review, setReview] = useState(false);
  const [outer, setOuter] = useState(false);
  const [history, setHistory] = useState<
    { version: number; document: PlanDoc }[]
  >([]);
  const [room, setRoom] = useState("");
  const svg = useRef<SVGSVGElement>(null);
  const measureDrag = useRef<number | null>(null);
  const live = useRef<PlanDoc | null>(null);
  const saved = useRef("");
  const version = useRef(0);
  const saving = useRef(false);
  const drag = useRef<{
    id: string;
    end: "start" | "end";
    before: PlanDoc;
  } | null>(null);
  const loaded = useRef("");
  const dirty = !!doc && JSON.stringify(doc) !== saved.current;
  const recoveryKey = "florp-plan-" + id;
  function edit(next: PlanDoc, history = true) {
    if (!doc) return;
    if (history) {
      setPast((p) => [...p.slice(-49), clone(doc)]);
      setFuture([]);
    }
    live.current = next;
    setDoc(next);
    setStatus("Unsaved changes");
  }
  async function persist(next: PlanDoc) {
    if (saving.current) return;
    saving.current = true;
    setStatus("Saving…");
    try {
      const result = await request<Workspace>(`/blueprints/${id}/workspace`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          expected_version: version.current,
          document: next,
        }),
      });
      version.current = result.version;
      saved.current = JSON.stringify(next);
      setState(result);
      if (JSON.stringify(live.current) === saved.current) {
        setStatus("Saved");
        localStorage.removeItem(recoveryKey);
      } else setStatus("Unsaved changes");
    } catch (e) {
      setError(String(e));
      setStatus("Save failed — edits retained locally");
    } finally {
      saving.current = false;
    }
  }
  async function extract(current: PlanDoc, v: number) {
    setBusy(true);
    setError("");
    setStatus("Finding walls and openings…");
    try {
      const result = await request<{ document: PlanDoc }>(
        `/blueprints/${id}/workspace/extract?expected_version=${v}`,
        { method: "POST" },
      );
      if (live.current !== current) {
        setError(
          "Extraction finished after another edit; existing edits were retained.",
        );
        return;
      }
      if (current.objects.length) {
        if (
          !window.confirm(
            "Replace this draft with a new extraction? Previous saved revisions are retained.",
          )
        )
          return;
        result.document.reference = current.reference;
        setPast((p) => [...p, clone(current)]);
      }
      live.current = result.document;
      setDoc(result.document);
      await persist(result.document);
    } catch (e) {
      setError(String(e));
      setStatus("Extraction needs attention");
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    let active = true;
    if (loaded.current === id) return;
    loaded.current = id;
    Promise.all([
      request<Workspace>(`/blueprints/${id}/workspace`),
      request<Blueprint>(`/blueprints/${id}/info`),
    ])
      .then(([result, info]) => {
        if (!active) return;
        setBp(info);
        version.current = result.version;
        saved.current = JSON.stringify(result.document);
        setState(result);
        let initial = result.document;
        const raw = localStorage.getItem(recoveryKey);
        if (raw) {
          try {
            const pending = JSON.parse(raw);
            if (pending.base === result.version) {
              initial = pending.document;
              setStatus("Recovered local changes");
            } else
              setError(
                "A recovery copy exists from an older revision. Download it before clearing browser storage.",
              );
          } catch {}
        }
        live.current = initial;
        setDoc(initial);
        if (!initial.objects.length && !raw)
          void extract(initial, result.version);
        else setStatus(raw ? "Recovered local changes" : "Saved");
      })
      .catch((e) => setError(String(e)));
    return () => {
      active = false;
      loaded.current = "";
    };
  }, [id]);
  useEffect(() => {
    if (!doc || !dirty) return;
    localStorage.setItem(
      recoveryKey,
      JSON.stringify({ base: version.current, document: doc }),
    );
    if (error || busy) return;
    const timer = setTimeout(() => {
      if (live.current) void persist(live.current);
    }, 800);
    return () => clearTimeout(timer);
  }, [doc, dirty, error, busy, state?.version]);
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
      if (e.key === "Escape") {
        setTool("select");
        setPoints([]);
      }
    };
    window.addEventListener("keydown", key);
    return () => window.removeEventListener("keydown", key);
  }, []);
  if (!doc) return <main className="pw-loading">{error || status}</main>;
  const d = doc,
    scale = ppm(d),
    item = d.objects.find((o) => o.id === selected),
    findings = d.objects.filter((o) => o.uncertain && !o.reviewed),
    currentRoom = state?.derived.rooms.find((r) => r.id === room);
  function point(e: React.PointerEvent<SVGSVGElement>): Pt {
    const matrix = svg.current?.getScreenCTM();
    if (!matrix) return { x: 0, y: 0 };
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(
      matrix.inverse(),
    );
    return {
      x: Math.max(0, Math.min(d.width, p.x)),
      y: Math.max(0, Math.min(d.height, p.y)),
    };
  }
  function choose(o: Object2D) {
    if (tool === "host" && item) {
      const next = attach(item, o);
      if (length(next) < 2) {
        setError("Choose a wall aligned with this opening");
        return;
      }
      edit({
        ...d,
        objects: d.objects.map((x) => (x.id === item.id ? next : x)),
      });
      setTool("select");
      return;
    }
    if (tool !== "select") return;
    setSelected(o.id);
    setRoom("");
  }
  function canvasClick(e: React.PointerEvent<SVGSVGElement>) {
    if (tool === "select" || tool === "host") return;
    const p = point(e);
    if (!points.length) {
      setPoints([p]);
      setPointer(p);
      return;
    }
    if (tool === "measure") {
      setPoints([points[0], p]);
      return;
    }
    const o: Object2D = {
      id: crypto.randomUUID(),
      kind: tool,
      start: points[0],
      end: p,
      thickness_px: 8,
      host_id: null,
      reviewed: true,
      uncertain: false,
      height_m: tool === "wall" ? 2.8 : tool === "door" ? 2.1 : 1.2,
      sill_m: tool === "window" ? 0.9 : 0,
    };
    if (length(o) < 2) return;
    edit({ ...d, objects: [...d.objects, o] });
    setSelected(o.id);
    setPoints([]);
    setTool(o.kind === "wall" ? "select" : "host");
  }
  function classify(kind: "wall" | "door" | "window" | "false") {
    if (!item) return;
    const provisionalHost = item.host_id?.startsWith("gap-host-")
      ? item.host_id
      : null;
    const sourceObjects =
      (kind === "false" || kind === "wall") && provisionalHost
        ? d.objects.filter((o) => o.id !== provisionalHost)
        : d.objects;
    const objects =
      kind === "false"
        ? sourceObjects
            .filter((o) => o.id !== item.id)
            .map((o) =>
              o.host_id === item.id
                ? { ...o, host_id: null, uncertain: true }
                : o,
            )
        : sourceObjects.map((o) =>
            o.id === item.id
              ? {
                  ...o,
                  kind,
                  reviewed: true,
                  uncertain: false,
                  host_id: kind === "wall" ? null : o.host_id,
                  height_m: kind === "wall" ? 2.8 : kind === "door" ? 2.1 : 1.2,
                  sill_m: kind === "window" ? 0.9 : 0,
                }
              : o.host_id === item.id && kind !== "wall"
                ? { ...o, host_id: null, uncertain: true }
                : o,
          );
    edit({ ...d, objects });
    if (
      kind !== "false" &&
      kind !== "wall" &&
      !objects.find((o) => o.id === item.id)?.host_id
    ) {
      setTool("host");
      return;
    }
    const next = findings.find((o) => o.id !== item.id);
    setSelected(next?.id || "");
  }
  function undo() {
    if (!past.length) return;
    const previous = past[past.length - 1];
    setFuture((f) => [clone(d), ...f]);
    setPast((p) => p.slice(0, -1));
    setSelected(
      previous.objects.find((o) => !d.objects.some((x) => x.id === o.id))?.id ||
        selected,
    );
    live.current = previous;
    setDoc(previous);
    setStatus(
      JSON.stringify(previous) === saved.current ? "Saved" : "Unsaved changes",
    );
  }
  function redo() {
    if (!future.length) return;
    const next = future[0];
    setPast((p) => [...p, clone(d)]);
    setFuture((f) => f.slice(1));
    live.current = next;
    setDoc(next);
    setStatus(
      JSON.stringify(next) === saved.current ? "Saved" : "Unsaved changes",
    );
  }
  function patch(values: Partial<Object2D>) {
    if (item)
      edit({
        ...d,
        objects: d.objects.map((o) =>
          o.id === item.id ? { ...o, ...values } : o,
        ),
      });
  }
  const rooms = dirty ? [] : state?.derived.rooms || [];
  return (
    <div className="pw">
      <header className="pw-header">
        <Link href={"/project/" + bp?.project_id}>✦ Florp</Link>
        <strong>{bp?.filename || "Floor plan"}</strong>
        <span role="status">{status}</span>
        <button disabled={!past.length || busy} onClick={undo}>
          Undo
        </button>
        <button disabled={!future.length || busy} onClick={redo}>
          Redo
        </button>
        <button onClick={() => setThree(false)} aria-pressed={!three}>
          2D
        </button>
        <button disabled={!scale} onClick={() => setThree(true)}>
          3D
        </button>
        <button
          disabled={!scale || dirty}
          onClick={() =>
            void import("../../../lib/exportPlan3D")
              .then((m) => m.exportPlan3D(d, rooms))
              .catch((e) => setError(String(e)))
          }
        >
          Export 3D
        </button>
        <a
          className={!scale || dirty ? "pw-disabled" : ""}
          href={`${API}/blueprints/${id}/workspace/export`}
        >
          Export plan
        </a>
      </header>
      <nav className="pw-tools">
        <button
          aria-pressed={tool === "select"}
          onClick={() => {
            setTool("select");
            setPoints([]);
          }}
        >
          Select
        </button>
        <button
          onClick={() => {
            setTool("measure");
            setPoints([]);
            setThree(false);
          }}
        >
          {scale ? "Change measurement" : "Set measurement"}
        </button>
        <button
          onClick={() => {
            setTool("wall");
            setPoints([]);
            setThree(false);
          }}
        >
          Add wall
        </button>
        <button
          onClick={() => {
            setTool("door");
            setPoints([]);
            setThree(false);
          }}
        >
          Add door
        </button>
        <button
          onClick={() => {
            setTool("window");
            setPoints([]);
            setThree(false);
          }}
        >
          Add window
        </button>
        <span className="pw-spacer" />
        <button onClick={() => setZoom((z) => Math.min(5, z * 1.25))}>+</button>
        <button onClick={() => setZoom((z) => Math.max(0.25, z / 1.25))}>
          −
        </button>
        <button onClick={() => setZoom(1)}>Fit</button>
        <button
          disabled={!d.objects.some((o) => o.exterior === true)}
          onClick={() => setOuter(!outer)}
        >
          {outer ? "All walls" : "Exterior only"}
        </button>
        <select
          aria-label="Plan view"
          value={view}
          onChange={(e) => setView(e.target.value as typeof view)}
        >
          <option value="clean">Clean</option>
          <option value="overlay">Overlay</option>
          <option value="original">Original</option>
        </select>
      </nav>
      {error && (
        <div className="pw-error" role="alert">
          {error}
          <button
            onClick={() => {
              setError("");
              if (live.current) void persist(live.current);
            }}
          >
            Retry save
          </button>
          <button
            onClick={() => {
              const a = document.createElement("a");
              a.href = URL.createObjectURL(
                new Blob(
                  [localStorage.getItem(recoveryKey) || JSON.stringify(d)],
                  { type: "application/json" },
                ),
              );
              a.download = "florp-recovery.json";
              a.click();
            }}
          >
            Download recovery
          </button>
        </div>
      )}
      <div className="pw-body">
        <section
          className="pw-canvas"
          aria-label="Plan viewport"
          onWheel={(e) => {
            if (e.ctrlKey || e.metaKey) {
              e.preventDefault();
              setZoom((z) =>
                Math.max(0.25, Math.min(5, z * (e.deltaY > 0 ? 0.9 : 1.1))),
              );
            }
          }}
        >
          {three ? (
            <div className="pw-three">
              <Viewer compact geometry={geometry(d, rooms)} />
            </div>
          ) : (
            <div
              style={{
                width: `${zoom * 100}%`,
                height: `${zoom * 100}%`,
                margin: "auto",
              }}
            >
              {" "}
              <svg
                ref={svg}
                viewBox={`0 0 ${d.width} ${d.height}`}
                style={{
                  width: "100%",
                  height: "100%",
                  minHeight: 500,
                  cursor: tool === "select" ? "default" : "crosshair",
                  touchAction: drag.current ? "none" : "auto",
                }}
                onPointerDown={canvasClick}
                onPointerMove={(e) => {
                  const p = point(e);
                  setPointer(p);
                  if (measureDrag.current !== null) {
                    setPoints((old) =>
                      old.map((q, i) => (i === measureDrag.current ? p : q)),
                    );
                    return;
                  }
                  if (drag.current && live.current) {
                    live.current = moveEndpoint(
                      live.current,
                      drag.current.id,
                      drag.current.end,
                      p,
                    );
                    setDoc(live.current);
                  }
                }}
                onPointerUp={() => {
                  measureDrag.current = null;
                  if (drag.current) {
                    const before = drag.current.before;
                    setPast((p) => [...p, before]);
                    setFuture([]);
                    drag.current = null;
                  }
                }}
              >
                <rect width={d.width} height={d.height} fill="white" />
                {view !== "clean" && (
                  <image
                    href={`${API}/blueprints/${id}/preview`}
                    width={d.width}
                    height={d.height}
                    opacity={view === "overlay" ? 0.65 : 1}
                  />
                )}
                {view !== "original" && (
                  <>
                    {rooms.map((r) => (
                      <polygon
                        key={r.id}
                        points={r.points.map((p) => `${p.x},${p.y}`).join(" ")}
                        fill={room === r.id ? "#d4eee8" : "#f0f8f5"}
                        stroke="none"
                        onPointerDown={(e) => {
                          if (tool !== "select") return;
                          e.stopPropagation();
                          setRoom(r.id);
                          setSelected("");
                        }}
                      />
                    ))}
                    {d.objects
                      .filter(
                        (o) =>
                          o.kind === "wall" && (!outer || o.exterior === true),
                      )
                      .map((o) => (
                        <g key={o.id}>
                          <line
                            x1={o.start.x}
                            y1={o.start.y}
                            x2={o.end.x}
                            y2={o.end.y}
                            stroke={selected === o.id ? "#e79430" : "#28515f"}
                            strokeWidth={o.thickness_px}
                          />
                          <line
                            x1={o.start.x}
                            y1={o.start.y}
                            x2={o.end.x}
                            y2={o.end.y}
                            stroke="transparent"
                            strokeWidth={Math.max(14, o.thickness_px)}
                            onPointerDown={(e) => {
                              if (tool === "select" || tool === "host") {
                                e.stopPropagation();
                                choose(o);
                              }
                            }}
                          />
                        </g>
                      ))}
                    {d.objects
                      .filter((o) => o.kind !== "wall")
                      .map((o) => (
                        <line
                          key={o.id}
                          x1={o.start.x}
                          y1={o.start.y}
                          x2={o.end.x}
                          y2={o.end.y}
                          stroke={
                            selected === o.id
                              ? "#e79430"
                              : o.kind === "window"
                                ? "#42b8c6"
                                : "white"
                          }
                          strokeWidth={Math.max(10, o.thickness_px + 2)}
                          onPointerDown={(e) => {
                            if (tool === "select") {
                              e.stopPropagation();
                              choose(o);
                            }
                          }}
                        />
                      ))}
                    {item &&
                      tool === "select" &&
                      (["start", "end"] as const).map((end) => (
                        <circle
                          key={end}
                          cx={item[end].x}
                          cy={item[end].y}
                          r={6 / Math.max(0.5, zoom)}
                          fill="white"
                          stroke="#e79430"
                          strokeWidth={2}
                          onPointerDown={(e) => {
                            e.stopPropagation();
                            e.currentTarget.setPointerCapture(e.pointerId);
                            drag.current = {
                              id: item.id,
                              end,
                              before: clone(d),
                            };
                          }}
                        />
                      ))}
                  </>
                )}
                {points.map((p, i) => (
                  <circle
                    key={"reference-" + i}
                    cx={p.x}
                    cy={p.y}
                    r={7}
                    fill="#ed8e22"
                    onPointerDown={(e) => {
                      e.stopPropagation();
                      e.currentTarget.setPointerCapture(e.pointerId);
                      measureDrag.current = i;
                    }}
                  />
                ))}
                {d.reference && (
                  <line
                    x1={d.reference.start[0]}
                    y1={d.reference.start[1]}
                    x2={d.reference.end[0]}
                    y2={d.reference.end[1]}
                    stroke="#008a73"
                    strokeWidth={2}
                    strokeDasharray="6 4"
                  />
                )}
                {points.length > 0 && (
                  <line
                    data-testid="measurement-line"
                    x1={points[0].x}
                    y1={points[0].y}
                    x2={(points[1] || pointer || points[0]).x}
                    y2={(points[1] || pointer || points[0]).y}
                    stroke="#ed8e22"
                    strokeWidth={3}
                  />
                )}
              </svg>
            </div>
          )}
        </section>
        <aside className="pw-inspector">
          {busy ? (
            <>
              <h2>Reading your plan</h2>
              <p>Building walls and checking openings…</p>
              <progress />
            </>
          ) : tool === "measure" ? (
            <>
              <h2>One known measurement</h2>
              <p>
                {points.length === 0
                  ? "Click the first reference point."
                  : points.length === 1
                    ? "Move the pointer, then click the second point."
                    : "Enter the real distance between the two points."}
              </p>
              {points.length === 2 && (
                <>
                  <label>
                    Distance
                    <input
                      aria-label="Known distance"
                      type="number"
                      min=".001"
                      value={distance}
                      onChange={(e) => setDistance(e.target.value)}
                    />
                  </label>
                  <select
                    aria-label="Distance unit"
                    value={unit}
                    onChange={(e) => setUnit(e.target.value)}
                  >
                    <option value="m">Meters</option>
                    <option value="cm">Centimeters</option>
                  </select>
                  <button
                    disabled={
                      !(Number(distance) > 0) ||
                      Math.hypot(
                        points[1].x - points[0].x,
                        points[1].y - points[0].y,
                      ) < 5
                    }
                    onClick={() => {
                      edit({
                        ...d,
                        reference: {
                          start: [points[0].x, points[0].y],
                          end: [points[1].x, points[1].y],
                          length_cm:
                            Number(distance) * (unit === "m" ? 100 : 1),
                        },
                      });
                      setTool("select");
                      setPoints([]);
                    }}
                  >
                    Use measurement
                  </button>
                  <button onClick={() => setPoints([])}>Place again</button>
                </>
              )}
              <button
                onClick={() => {
                  setTool("select");
                  setPoints([]);
                }}
              >
                Cancel
              </button>
            </>
          ) : item ? (
            <>
              <small>{review ? "REVIEW FINDING" : "SELECTED OBJECT"}</small>
              <h2>
                {item.kind === "wall"
                  ? "Wall"
                  : item.kind === "door"
                    ? "Door"
                    : "Window"}
              </h2>
              <p>
                {scale
                  ? (length(item) / scale).toFixed(2) + " m"
                  : "Set one measurement to see dimensions"}
              </p>
              <div className="pw-decisions">
                {(["wall", "door", "window", "false"] as const).map((k) => (
                  <button key={k} onClick={() => classify(k)}>
                    {k === "false" ? "False detection" : k}
                  </button>
                ))}
              </div>
              {item.kind !== "wall" && (
                <button onClick={() => setTool("host")}>
                  {tool === "host"
                    ? "Click its wall on the plan"
                    : "Choose host wall"}
                </button>
              )}
              <label>
                Thickness ({scale ? "m" : "px"})
                <input
                  type="number"
                  min=".01"
                  value={Number((item.thickness_px / (scale || 1)).toFixed(3))}
                  onChange={(e) =>
                    Number(e.target.value) > 0 &&
                    patch({
                      thickness_px: Number(e.target.value) * (scale || 1),
                    })
                  }
                />
              </label>
              <label>
                Height (m)
                <input
                  type="number"
                  min=".1"
                  max="20"
                  value={item.height_m}
                  onChange={(e) =>
                    Number(e.target.value) > 0 &&
                    patch({ height_m: Number(e.target.value) })
                  }
                />
              </label>
              {item.kind === "window" && (
                <label>
                  Sill height (m)
                  <input
                    type="number"
                    min="0"
                    value={item.sill_m}
                    onChange={(e) =>
                      patch({ sill_m: Math.max(0, Number(e.target.value)) })
                    }
                  />
                </label>
              )}
              <small>
                Drag the two handles to adjust. Connected endpoints move
                together.
              </small>
              <button
                onClick={() => {
                  const index = findings.findIndex((o) => o.id === item.id);
                  setSelected(
                    findings[(index - 1 + findings.length) % findings.length]
                      ?.id || "",
                  );
                }}
              >
                Previous finding
              </button>
              <button
                onClick={() => {
                  const next =
                    findings[
                      (findings.findIndex((o) => o.id === item.id) + 1) %
                        findings.length
                    ];
                  setSelected(next?.id || "");
                }}
              >
                Next finding
              </button>
            </>
          ) : currentRoom ? (
            <>
              <h2>Room</h2>
              {!scale && <p>Set one measurement to see room dimensions.</p>}
              {scale && (
                <details>
                  <summary>Boundary lengths</summary>
                  {currentRoom.points.map((p, i) => {
                    const q =
                      currentRoom.points[(i + 1) % currentRoom.points.length];
                    return (
                      <p key={i}>
                        Side {i + 1}:{" "}
                        {(Math.hypot(p.x - q.x, p.y - q.y) / scale).toFixed(2)}{" "}
                        m
                      </p>
                    );
                  })}
                </details>
              )}
              <p>{currentRoom.area_m2?.toFixed(2)} m² usable floor area</p>
              {currentRoom.width_m && (
                <p>
                  {currentRoom.width_m.toFixed(2)} ×{" "}
                  {currentRoom.depth_m?.toFixed(2)} m clear dimensions
                </p>
              )}
            </>
          ) : (
            <>
              <small>YOUR FLOOR PLAN</small>
              <h2>
                {scale
                  ? "Measured plan"
                  : d.objects.length
                    ? "Your walls are ready"
                    : "Plan needs attention"}
              </h2>
              <p>
                {scale
                  ? "Select a wall, opening or room to inspect it."
                  : "Set one known measurement to calculate physical sizes."}
              </p>
              <button
                disabled={!findings.length}
                onClick={() => {
                  setReview(true);
                  setSelected(findings[0]?.id || "");
                }}
              >
                Review {findings.length} findings
              </button>
              <p>
                {d.objects.filter((o) => o.kind === "wall").length} walls ·{" "}
                {d.objects.filter((o) => o.kind !== "wall").length} openings
              </p>
              <p>{rooms.length} enclosed rooms</p>
              {!dirty && state?.derived.footprint_area_m2 && (
                <p>
                  Enclosed footprint:{" "}
                  {state.derived.footprint_area_m2.toFixed(2)} m²
                </p>
              )}
              {scale && state?.derived.bounds_px && (
                <p>
                  Overall extents:{" "}
                  {(
                    (state.derived.bounds_px[2] - state.derived.bounds_px[0]) /
                    scale
                  ).toFixed(2)}{" "}
                  ×{" "}
                  {(
                    (state.derived.bounds_px[3] - state.derived.bounds_px[1]) /
                    scale
                  ).toFixed(2)}{" "}
                  m
                </p>
              )}
              <details>
                <summary>Source notes</summary>
                {d.warnings.map((w, i) => (
                  <p key={i}>{w}</p>
                ))}
              </details>
              <details
                onToggle={(e) => {
                  if (e.currentTarget.open)
                    void request<{ version: number; document: PlanDoc }[]>(
                      `/blueprints/${id}/workspace/history`,
                    )
                      .then(setHistory)
                      .catch((e) => setError(String(e)));
                }}
              >
                <summary>Saved history</summary>
                {history.map((h) => (
                  <button
                    key={h.version}
                    onClick={() => {
                      if (
                        window.confirm(
                          "Restore revision " +
                            h.version +
                            "? Current saved history is retained.",
                        )
                      )
                        edit(h.document);
                    }}
                  >
                    Restore revision {h.version}
                  </button>
                ))}
              </details>
              <details>
                <summary>Re-extract plan</summary>
                <p>
                  Saved history is retained; replacement requires confirmation.
                </p>
                <button
                  disabled={dirty || busy}
                  onClick={() => void extract(d, version.current)}
                >
                  Re-extract
                </button>
              </details>
            </>
          )}
          {!scale && three && <p>Set one measurement first.</p>}
        </aside>
      </div>
      <footer className="pw-footer">
        <span>{scale ? "Reference measurement set" : "Scale not set"}</span>
        <span>{findings.length} findings</span>
        <span>Default wall height 2.8 m · editable per object</span>
        <Link href={"/blueprint/" + id + "/legacy"}>Historical editor</Link>
      </footer>
    </div>
  );
}
