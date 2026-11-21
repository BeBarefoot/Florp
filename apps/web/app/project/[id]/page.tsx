"use client";
import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { API, request, Blueprint } from "../../../lib/api";
import FloorPairReview from "../../../components/FloorPairReview";
export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const [plans, setPlans] = useState<Blueprint[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const file = useRef<HTMLInputElement>(null);
  const uploaded = useRef(new WeakSet<File>());
  useEffect(() => {
    request<Blueprint[]>(`/projects/${id}/blueprints`)
      .then(setPlans)
      .catch((e) => setError(String(e)));
  }, [id]);
  async function upload(files = Array.from(file.current?.files??[])) {
    if (!files.length || busy) return;
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
      if(lastId && files.length===1 && !plans.length)window.location.href = (matchMedia("(pointer:coarse)").matches?"/phone/":"/plan/") + lastId;
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="app">
      <aside>
        <h2>✦ Florp</h2>
        <p>
          <Link href="/">← All projects</Link>
        </p>
        <p>Floor plans</p>
      </aside>
      <main>
        <header>
          <div>
            <h1>Project workspace</h1>
            <p className="muted">Upload PDF, PNG or JPG floor plans.</p>
          </div>
        </header>
        <div
          className="panel stack"
          style={{ marginBottom: 20 }}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            if (file.current && !busy) {
              file.current.files = e.dataTransfer.files;
              void upload();
            }
          }}
        >
          <h2>Upload blueprint</h2>
          <p>Choose both floor pictures together or add another drawing to this project.</p>
          <input
            aria-label="Floor plan file"
            ref={file}
            type="file" multiple
            accept="application/pdf,image/png,image/jpeg,image/webp"
          />
          <label className="plan-photo">Take a plan photo
            <input type="file" accept="image/jpeg,image/png" capture="environment" disabled={busy}
              onChange={event=>{
                const photo = event.currentTarget.files?.[0];
                event.currentTarget.value = "";
                if (photo) void upload([photo]);
              }}/>
          </label>
          <div>
            <button disabled={busy} onClick={()=>void upload()}>
              {busy ? "Uploading…" : "Upload plan"}
            </button>
          </div>
          <small className="muted">
            One floor per upload. PDFs use the first page only; export other pages separately. PNG, JPEG and WebP supported. Maximum decoded size: 45 megapixels.
          </small>
        </div>
        {error && <p role="alert" className="notice">{error}</p>}
        {plans.length>=2&&<FloorPairReview pid={id} plans={plans}/>}
        <div className="grid">
          {plans.map((p) => (
            <div className="panel" key={p.id}><Link href={"/plan/" + p.id}>
              <img
                src={`${API}/blueprints/${p.id}/preview`}
                alt="Blueprint preview"
                style={{
                  width: "100%",
                  height: 190,
                  objectFit: "contain",
                  background: "#f2f4f7",
                }}
              />
              <h2>{p.filename}</h2>
              <p className="muted">
                {p.width} × {p.height}px · Open editor →
              </p>
            </Link><Link className="phone-open" href={"/phone/"+p.id}>Open phone walkthrough →</Link></div>
          ))}
        </div>
      </main>
    </div>
  );
}
