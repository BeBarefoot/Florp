"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowUpRight, Box, Folder, Trash2, Upload } from "lucide-react";
import DesktopBrand from "../components/DesktopBrand";
import { newUuid } from "../lib/uuid";
import { API, request, type Blueprint, type Project } from "../lib/api";

export default function Home() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [health, setHealth] = useState("Checking local connection");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [preview, setPreview] = useState<Blueprint | null>(null);
  const [picked, setPicked] = useState<File | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const inFlight = useRef(false);
  const pending = useRef<{ file: File; id: string } | null>(null);

  useEffect(() => {
    request<Project[]>("/projects").then(setProjects).catch(problem => setError(String(problem)));
    request<{ok: boolean}>("/health").then(result => setHealth(result.ok ? "Mac host ready" : "Local host unavailable"))
      .catch(() => setHealth("Local host unavailable"));
  }, []);

  async function upload(file: File) {
    if (inFlight.current) return;
    inFlight.current = true;
    setPicked(file);
    setBusy(true);
    setError("");
    setPreview(null);
    try {
      const uploadId = pending.current?.file === file ? pending.current.id : newUuid();
      pending.current = { file, id: uploadId };
      const data = new FormData();
      data.append("file", file);
      const floor = await request<Blueprint>(`/home-uploads/${uploadId}`, { method: "POST", body: data });
      const project = { id: floor.project_id, title: floor.filename.replace(/\.[^.]+$/, "") };
      setProjects(current => [project, ...current.filter(home => home.id !== project.id)]);
      pending.current = null;
      setPicked(null);
      setPreview(floor);
    } catch (problem) {
      setError(String(problem));
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  async function removeProject(project: Project) {
    if (!window.confirm(`Delete “${project.title}” and its floor plans and renders?`)) return;
    try {
      await request(`/projects/${encodeURIComponent(project.id)}`, { method: "DELETE" });
      setProjects(current => current.filter(home => home.id !== project.id));
      if (preview?.project_id === project.id) setPreview(null);
    } catch (problem) {
      setError(String(problem));
    }
  }

  const [latest, ...others] = projects;
  return <main className="desktop-home desktop-surface">
    <header className="desktop-mast"><DesktopBrand/><span className="desktop-connection" role="status">{health}</span></header>
    <section className="desktop-home-hero" data-dragging={dragging}
      onDragOver={event => { event.preventDefault(); setDragging(true); }}
      onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false); }}
      onDrop={event => {
        event.preventDefault();
        setDragging(false);
        const file = event.dataTransfer.files[0];
        if (file) void upload(file);
      }}>
      <div className="desktop-home-copy">
      {preview ? <>
        <h1>{preview.filename}</h1>
        {preview.filename.toLowerCase().endsWith(".pdf") && <p>PDF · Page 1</p>}
        <button className="desktop-primary" onClick={() => router.push("/plan/" + encodeURIComponent(preview.id) + "?review=1")}>
          Analyze plan <ArrowUpRight size={17}/>
        </button>
        <button onClick={() => input.current?.click()}>Choose another file</button>
      </> : <>
        <h1>Walk your<br/>future home.</h1>
        <p>Turn a floor plan into a home you can walk through, furnish, and make your own.</p>
        <button className="desktop-primary" disabled={busy} onClick={() => input.current?.click()}>
          <Upload size={17}/>{busy ? "Opening drawing…" : "Upload a plan"}
        </button>
        <Link href="/studio/sample"><Box size={17}/> Explore a sample</Link>
      </>}
      </div>
      <figure className="desktop-home-image" data-preview={!!preview}>
        {preview ? <img src={`${API}/blueprints/${preview.id}/preview`} alt="Drawing ready for extraction"/>
          : <img src="/desktop-interior.webp" alt="Sunlit living room with a warm timber floor"/>}
      </figure>
      <input ref={input} type="file" accept=".pdf,.png,.jpeg,.jpg,.webp" hidden onChange={event => {
        const file = event.currentTarget.files?.[0];
        event.currentTarget.value = "";
        if (file) void upload(file);
      }}/>
      {error && <div className="desktop-home-error" role="alert">{error}
        {picked && <button disabled={busy} onClick={() => void upload(picked)}>Retry upload</button>}</div>}
    </section>
    {latest && <section className="desktop-recents" aria-label="Recent homes">
      <h2>Recent homes</h2>
      <ul>{[latest, ...others].map(project => <li key={project.id}>
        <Link href={"/project/" + project.id}><Folder size={18}/><span>{project.title}</span><ArrowUpRight size={16}/></Link>
        <button type="button" aria-label={`Delete ${project.title}`} onClick={() => void removeProject(project)} title="Delete home"><Trash2 size={16}/></button>
      </li>)}</ul>
    </section>}
  </main>;
}
