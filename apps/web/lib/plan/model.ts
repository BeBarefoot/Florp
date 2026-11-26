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
export type WindowFrame = { material: "wood" | "aluminium" | "vinyl"; color: string; widthM: number; panes: 1 | 2 };
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
  windowFrame?: WindowFrame | null;
};
export type RoomType = "bedroom" | "garage" | "bathroom" | "kitchen" | "corridor" | "balcony" | "other";
export const ROOM_TYPES: RoomType[] = ["bedroom", "garage", "bathroom", "kitchen", "corridor", "balcony", "other"];
export type Room = {
  id: string;
  wallIds: string[];
  polygon: Pt[];
  areaPx2: number;
  label: string | null;
  roomType?: RoomType | null;
  ceilingHeightM?: number | null;
  needsSemanticReview?: boolean;
};
export type StairDirection = "up" | "down" | "both";
export type Stair = { id: string; layout: "l" | "u"; treads: Pt[][]; riseM: number;
  direction?: StairDirection; treadsBelow?: number | null };
export type FindingCategory =
  | "opening_needs_approval"
  | "suggested_closure"
  | "open_wall_end"
  | "low_confidence_wall"
  | "unclosed_region"
  | "pruned_fragments"
  | "merged_duplicates"
  | "open_passage";
export type Finding = {
  closure?: {start:Pt;end:Pt;thicknessPx:number} | null;
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
  extractionVersion?: number | null;
  gardens?: import("../api").SiteRegion[];
  schemaVersion: 2;
  id: string;
  revision: number;
  imageTransform: { width: number; height: number; rotation: number };
  scale: {
    metersPerPixel: number | null;
    reference: Reference | null;
    checkReference?: Reference | null;
    proposal?: { reference: Reference; checkReference: Reference; evidenceCount: number };
  };
  nodes: Node[];
  walls: Wall[];
  openings: Opening[];
  stairs?: Stair[];
  roomSymbols?: { kind: "car" | "bed" | "sofa" | "dining_table" | "bar_stools" | "cooktop" | "coffee_table" | "tree" | "sink" | "toilet" | "cabinets" | "patio_set" | "bar_counter" | "tv_console" | "fridge"; position: Pt; widthPx?: number | null; depthPx?: number | null; rotation?: number }[];
  rooms: Room[];
  roomZones?: Omit<Room, "wallIds" | "areaPx2">[];
  findings: Finding[];
  envelope?: Pt[] | null;
  dismissedFindings: string[];
  notes: string[];
};
export type PlanResponse = { revision: number; model: PlanModel | null; latestExtractionVersion?: number };
export const FINDING_LABELS: Record<FindingCategory, string> = {
  opening_needs_approval: "Needs your approval",
  suggested_closure: "Suggested wall closures",
  open_wall_end: "Open wall ends",
  low_confidence_wall: "Low-confidence walls",
  unclosed_region: "Unclosed rooms",
  pruned_fragments: "Removed fragments",
  merged_duplicates: "Merged duplicates",
  open_passage: "Open passages (no door symbol)",
};
