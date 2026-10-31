"use client";
import Link from "next/link";
import { AppWindow, BrickWall, Crop, DoorOpen, FolderOpen, MousePointer2, RefreshCw, Ruler } from "lucide-react";
import type { Tool, ViewMode } from "./types";

const TOOLS: { id: Tool; label: string; key: string; icon: React.ReactNode }[] = [
  { id: "select", label: "Select", key: "V", icon: <MousePointer2 size={18} /> },
  { id: "measure", label: "Set measurement", key: "M", icon: <Ruler size={18} /> },
  { id: "wall", label: "Add wall", key: "W", icon: <BrickWall size={18} /> },
  { id: "door", label: "Add door", key: "D", icon: <DoorOpen size={18} /> },
  { id: "window", label: "Add window", key: "N", icon: <AppWindow size={18} /> },
];

export default function ToolRail(p: {
  projectHref: string;
  tool: Tool;
  setTool: (t: Tool) => void;
  view: ViewMode;
  setView: (v: ViewMode) => void;
  onStraighten: () => void;
  onReextract: () => void;
  busy: boolean;
}) {
  return (
    <nav className="fe-rail" aria-label="Tools">
      <Link href={p.projectHref} className="fe-tool" title="Projects" aria-label="Projects">
        <FolderOpen size={18} />
      </Link>
      <hr />
      {TOOLS.map((t) => (
        <button
          key={t.id}
          className="fe-tool"
          aria-pressed={p.tool === t.id}
          aria-label={t.label}
          title={`${t.label} (${t.key})`}
          onClick={() => p.setTool(t.id)}
        >
          {t.icon}
        </button>
      ))}
      <span className="fe-spacer" />
      <div className="fe-views" role="radiogroup" aria-label="Plan view">
        {(["clean", "overlay", "original"] as const).map((v) => (
          <button key={v} role="radio" aria-checked={p.view === v} title={v} onClick={() => p.setView(v)}>
            {v[0].toUpperCase()}
          </button>
        ))}
      </div>
      <button className="fe-tool" title="Straighten photographed sheet" aria-label="Straighten photographed sheet" disabled={p.busy} onClick={p.onStraighten}>
        <Crop size={18} />
      </button>
      <button className="fe-tool" title="Re-extract from drawing" aria-label="Re-extract from drawing" disabled={p.busy} onClick={p.onReextract}>
        <RefreshCw size={18} />
      </button>
    </nav>
  );
}
