// Mirrors apps/api/app/plan_model.py (PlanModel v2). Pixel space only.
export type Pt = { x: number; y: number };
export type Node = { id: string; x: number; y: number };
export type Wall = {
  id: string;
  a: string;
  b: string;
  thicknessPx: number;
  heightM: number;
  material: "block" | "concrete";
  exterior: boolean | null;
  confidence: number;
  source: "extracted" | "user";
};
export type OpeningStatus = "proposed" | "confirmed" | "rejected";
export type Opening = {
  id: string;
  kind: "door" | "window" | "garage";
  hostWallId: string | null;
  offsetPx: number;
  widthPx: number;
  span: [Pt, Pt] | null;
  heightM: number;
  sillM: number;
  swing: "left" | "right" | null;
  hinge: "start" | "end";
  confidence: number;
  status: OpeningStatus;
};
export type Room = {
  id: string;
  wallIds: string[];
  polygon: Pt[];
  areaPx2: number;
  label: string | null;
};
export type FindingCategory =
  | "opening_needs_approval"
  | "open_wall_end"
  | "low_confidence_wall"
  | "unclosed_region"
  | "pruned_fragments"
  | "merged_duplicates"
  | "open_passage";
export type Finding = {
  id: string;
  category: FindingCategory;
  severity: "info" | "warn";
  targetIds: string[];
  anchor: Pt;
  count: number;
  message: string;
};
export type Reference = { p1: Pt; p2: Pt; lengthMeters: number };
export type PlanModel = {
  schemaVersion: 2;
  id: string;
  revision: number;
  imageTransform: { width: number; height: number; rotation: number };
  scale: { metersPerPixel: number | null; reference: Reference | null };
  nodes: Node[];
  walls: Wall[];
  openings: Opening[];
  rooms: Room[];
  findings: Finding[];
  envelope?: Pt[] | null;
  dismissedFindings: string[];
  notes: string[];
};
export type PlanResponse = { revision: number; model: PlanModel | null };
export const FINDING_LABELS: Record<FindingCategory, string> = {
  opening_needs_approval: "Needs your approval",
  open_wall_end: "Open wall ends",
  low_confidence_wall: "Low-confidence walls",
  unclosed_region: "Unclosed rooms",
  pruned_fragments: "Removed fragments",
  merged_duplicates: "Merged duplicates",
  open_passage: "Open passages (no door symbol)",
};
