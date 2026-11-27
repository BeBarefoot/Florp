"use client";
import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowUpRight, Box, ChevronRight, FileImage, Plus } from "lucide-react";
import DesktopBrand from "../../../components/DesktopBrand";
import { useParams } from "next/navigation";
import { API, request, Blueprint, Project } from "../../../lib/api";
import FloorPairReview from "../../../components/FloorPairReview";
export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const [plans, setPlans] = useState<Blueprint[]>([]);
  const [project, setProject] = useState<Project>();
  const [loadError, setLoadError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [queued, setQueued] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const file = useRef<HTMLInputElement>(null);
  const uploaded = useRef(new WeakSet<File>());
  useEffect(() => {
    let active = true;
    request<Blueprint[]>(`/projects/${id}/blueprints`)
      .then(floors => { if (active) setPlans(floors); })
      .catch(problem => { if (active) setLoadError(String(problem)); })
      .finally(() => { if (active) setLoaded(true); });
    request<Project[]>("/projects").then(homes => {
      if (active) setProject(homes.find(home => home.id === id));
    }).catch(() => {});
    return () => { active = false; };
  }, [id]);
  useEffect(() => {
    if (window.location.hash === "#add-floor") file.current?.focus();
  }, [id]);
  const uploadInFlight = useRef(false);
  async function upload(files = queued) {
    if (!files.length || uploadInFlight.current) return;
    uploadInFlight.current = true;
    setBusy(true);
    setError("");
    try {
      let lastId="";
      for(const f of files){
        if(uploaded.current.has(f))continue;
        const data = new FormData();
        data.append("file", f);
        const r = await fetch(
          `${API}/projects/${id}/blueprints`,
          { method: "POST", body: data },
        );
        if (!r.ok) {
          const problem = await r.json().catch(() => null);
          throw Error(problem?.detail || "Upload failed. Please try again.");
        }
        const bp = await r.json();
        setPlans(current=>[bp,...current]);
        uploaded.current.add(f);
        lastId=bp.id;
      }
      if (file.current) file.current.value = "";
      setQueued([]);
      if(lastId && files.length===1 && !plans.length)window.location.href = (matchMedia("(pointer:coarse)").matches?"/phone/"+lastId:"/plan/"+lastId+"?review=1");
    } catch (e) {
      setError(String(e));
    } finally {
      uploadInFlight.current = false;
      setBusy(false);
    }
  }
  return <div className="desktop-project desktop-surface">
    <header className="desktop-mast">
      <DesktopBrand/>
      <nav className="desktop-breadcrumb" aria-label="Breadcrumb">
        <Link href="/">Homes</Link><ChevronRight size={14}/><span aria-current="page">{project?.title || "Project"}</span>
      </nav>
      <Link className="desktop-back" href="/"><ArrowLeft size={16}/> All homes</Link>
    </header>
    <main className="project-content">
      <div className="project-heading">
        <h1>{project?.title || "Project workspace"}</h1>
        {plans.length > 0 && <span>{plans.length} {plans.length === 1 ? "floor plan" : "floor plans"}</span>}
      </div>
      <div className="project-grid">
        <section className="project-library" aria-labelledby="project-floors">
          <h2 id="project-floors">Floor plans</h2>
          {!loaded && <p role="status">Opening your plans…</p>}
          {loadError && <p className="desktop-error" role="alert">{loadError}</p>}
          {loaded && !loadError && !plans.length && <div className="project-empty"><FileImage size={28}/><p>Add a drawing to open your first floor.</p></div>}
          <div className="project-floor-grid">
            {plans.map(plan => <article className="project-floor" key={plan.id}>
              <Link className="project-preview" href={"/plan/" + plan.id} aria-label={`Edit ${plan.filename}`}>
                <img src={`${API}/blueprints/${plan.id}/preview`} alt="Floor plan drawing"/>
              </Link>
              <div className="project-floor-details">
                <h3 title={plan.filename}>{plan.filename}</h3>
                {plan.floor && <p>{plan.floor.level === 1 ? "First floor" : "Second floor"}</p>}
                <div className="project-floor-actions">
                  <Link className="desktop-action primary" href={"/plan/" + plan.id}>Open plan <ArrowUpRight size={15}/></Link>
                  <Link className="desktop-action" href={`/studio/${plan.id}#overview`}><Box size={16}/> 3D studio</Link>
                  <Link className="project-phone-link" href={"/phone/" + plan.id}>Phone walkthrough</Link>
                </div>
              </div>
            </article>)}
          </div>
          {plans.length >= 2 && <FloorPairReview pid={id} plans={plans}/>}
        </section>
        <section id="add-floor" className="project-upload" aria-labelledby="project-upload-title" data-dragging={dragging}
          onDragOver={event => { event.preventDefault(); setDragging(true); }}
          onDragLeave={event => {
            if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
          }}
          onDrop={event => {
            event.preventDefault();
            setDragging(false);
            if (uploadInFlight.current) return;
            if (file.current) file.current.value = "";
            setQueued(Array.from(event.dataTransfer.files));
          }}>
          <h2 id="project-upload-title">Add a floor</h2>
          <label className="project-drop">
            <Plus size={23}/>
            <span>Choose files</span>
            <small>or drop drawings here</small>
            <input aria-label="Floor plan file" ref={file} type="file" multiple disabled={busy}
              accept="application/pdf,image/png,image/jpeg,image/webp"
              onChange={event => setQueued(Array.from(event.currentTarget.files ?? []))}/>
          </label>
          <label className="plan-photo">Take a plan photo
            <input type="file" accept="image/jpeg,image/png" capture="environment" disabled={busy}
              onChange={event => {
                const photo = event.currentTarget.files?.[0];
                event.currentTarget.value = "";
                if (photo) void upload([photo]);
              }}/>
          </label>
          {queued.length > 0 && <ul className="project-queued" aria-label="Files to upload">
            {queued.map((drawing, index) => <li key={`${drawing.name}-${index}`}><FileImage size={16}/><span>{drawing.name}</span></li>)}
          </ul>}
          <button className="desktop-action primary" disabled={busy || !queued.length} onClick={() => void upload()}>
            {busy ? "Uploading…" : "Upload plan"}
          </button>
          {error && <p className="desktop-error" role="alert">{error}</p>}
          <small>PDFs use the first page only. PNG, JPEG and WebP are also supported. Maximum 45 megapixels per drawing.</small>
        </section>
      </div>
    </main>
  </div>;
}
