"use client";
import { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { API, request, Blueprint } from "../../../lib/api";
export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const [plans, setPlans] = useState<Blueprint[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);
  const file = useRef<HTMLInputElement>(null);
  useEffect(() => {
    request<Blueprint[]>(`/projects/${id}/blueprints`)
      .then(setPlans)
      .catch((e) => setError(String(e)));
  }, [id]);
  async function upload() {
    const f = file.current?.files?.[0];
    if (!f) return;
    setBusy(true);
    setError("");
    try {
      const data = new FormData();
      data.append("file", f);
      const r = await fetch(
        `${API}/projects/${id}/blueprints?page_index=${page - 1}`,
        { method: "POST", body: data },
      );
      if (!r.ok) throw Error(await r.text());
      const bp = await r.json();
      setPlans([bp, ...plans]);
      if (file.current) file.current.value = "";
      window.location.href = "/plan/" + bp.id;
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
          <p>Drop a plan here or choose a file.</p>
          <input
            ref={file}
            type="file"
            accept="application/pdf,image/png,image/jpeg,image/webp"
          />
          <label>
            PDF page{" "}
            <input
              aria-label="PDF page"
              type="number"
              min="1"
              value={page}
              onChange={(e) => setPage(Math.max(1, Number(e.target.value)))}
            />
          </label>
          <div>
            <button disabled={busy} onClick={upload}>
              {busy ? "Uploading…" : "Upload plan"}
            </button>
          </div>
          <small className="muted">
            Choose the page for multi-page PDFs. Max size configured on backend.
          </small>
        </div>
        {error && <p className="notice">{error}</p>}
        <div className="grid">
          {plans.map((p) => (
            <Link className="panel" key={p.id} href={"/plan/" + p.id}>
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
            </Link>
          ))}
        </div>
      </main>
    </div>
  );
}
