import {request} from "../api";
import {newUuid} from "../uuid";
import type {PlanResponse, Pt} from "./model";

export type ExtractionProgress = {percent: number; stage: string};

export async function extractWithProgress(
  base: string, revision: number, onProgress: (progress: ExtractionProgress) => void, envelope?: Pt[],
) {
  const id = newUuid();
  let active = true;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const controller = new AbortController();
  async function poll() {
    try {
      const state = await request<ExtractionProgress | null>(`${base}/plan/extraction-progress/${id}`,
        {signal: controller.signal});
      if (active && state) onProgress(state);
    } catch {
      // Extraction itself can continue if a progress request fails.
    }
    if (active) timer = setTimeout(poll, 350);
  }
  onProgress({percent: 0, stage: "Opening drawing"});
  timer = setTimeout(poll, 150);
  try {
    const result = await request<PlanResponse>(`${base}/plan/extract?expected_revision=${revision}`, {
      method: "POST",
      headers: {"X-Florp-Progress-Id": id, ...(envelope ? {"Content-Type": "application/json"} : {})},
      body: envelope ? JSON.stringify({envelope}) : undefined,
    });
    onProgress({percent: 100, stage: "Plan ready"});
    return result;
  } finally {
    active = false;
    controller.abort();
    clearTimeout(timer);
  }
}
