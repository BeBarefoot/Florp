"use client";
import { useState } from "react";
import { ArrowLeft, Box, Columns2, Download, Footprints, Redo2, Smartphone, Undo2 } from "lucide-react";

import Link from "next/link";
import DesktopBrand from "../DesktopBrand";

export type Display = "2d" | "3d" | "split";

export default function TopBar(p: {
  title: string;
  projectHref: string;
  status: string;
  extractionAction?: React.ReactNode;
  dirty: boolean;
  onSave: () => void;
  canUndo: boolean;
  canRedo: boolean;
  undo: () => void;
  redo: () => void;
  display: Display;
  setDisplay: (d: Display) => void;
  scaled: boolean;
  onWalkthrough: () => void;
  onPhoneWalkthrough: () => void;
  onOverview: () => void;
  reviewAction: React.ReactNode;
  walkthroughBusy: boolean;
  exportBlocker: string | null;
  exportPlanHref: string;
  debugHref: string;
  export3D: () => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <header className="fe-top">
      <div className="editor-mast">
        <DesktopBrand/>
        <Link href={p.projectHref} className="editor-back" aria-label="Back to project"><ArrowLeft size={16}/></Link>
        <span className="fe-title" title={p.title}>{p.title}</span>
        <div className="editor-modes" role="group" aria-label="Workspace views">
          <button aria-pressed="true" onClick={() => p.setDisplay("2d")}>Plan</button>
          <button disabled={p.walkthroughBusy} onClick={p.onOverview}><Box size={15}/>Overview</button>
          <button disabled={p.walkthroughBusy} onClick={p.onWalkthrough}><Footprints size={15}/>Walk</button>
        </div>
        <span className="fe-status" role="status">{p.status}</span>
        <button className="fe-primary" disabled={!p.dirty} onClick={p.onSave}>Save</button>
      </div>
      <div className="editor-actions">
        <button aria-label="Undo" title="Undo (Ctrl+Z)" disabled={!p.canUndo} onClick={p.undo}><Undo2 size={16} /></button>
        <button aria-label="Redo" title="Redo (Ctrl+Shift+Z)" disabled={!p.canRedo} onClick={p.redo}><Redo2 size={16} /></button>
        <div className="fe-segment" role="radiogroup" aria-label="Display">
          <button role="radio" aria-checked={p.display === "2d"} onClick={() => p.setDisplay("2d")}>2D</button>
          <button role="radio" aria-checked={p.display === "split"} disabled={!p.scaled} title={p.scaled ? "" : "Set one measurement first"} onClick={() => p.setDisplay("split")}><Columns2 size={14} /></button>
          <button role="radio" aria-checked={p.display === "3d"} disabled={!p.scaled} title={p.scaled ? "" : "Set one measurement first"} onClick={() => p.setDisplay("3d")}><Box size={14} /> 3D</button>
        </div>
        {p.reviewAction}
        {p.extractionAction}
        <span className="fe-spacer"/>
        <button aria-label="Phone walkthrough" title="Phone walkthrough" disabled={p.walkthroughBusy} onClick={p.onPhoneWalkthrough}><Smartphone size={17}/></button>
        <div className="fe-menu">
          <button aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}><Download size={16} /> Export</button>
          {open && (
            <div role="menu" className="fe-menu-list" onClick={() => setOpen(false)}>
              {p.exportBlocker ? <p className="fe-muted">{p.exportBlocker}</p> : null}
              <a role="menuitem" aria-disabled={!!p.exportBlocker} className={p.exportBlocker ? "disabled" : ""} href={p.exportBlocker ? undefined : p.exportPlanHref}>
                Plan bundle (DXF, SVG, PNG)
              </a>
              <a role="menuitem" href={p.debugHref}>Extraction diagnostics (.zip)</a>
              <button role="menuitem" disabled={!!p.exportBlocker} onClick={p.export3D}>3D model (.glb)</button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
