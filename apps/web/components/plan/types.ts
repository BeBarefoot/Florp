import type { Pt } from "../../lib/plan/model";
export type Tool = "select" | "measure" | "wall" | "door" | "window" | "attach" | "straighten";
export type Selection = { type: "wall" | "opening" | "room"; id: string } | null;
export type ViewMode = "clean" | "overlay" | "original";
export type Focus = { point: Pt; nonce: number } | null;
