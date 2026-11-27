import type {ExtractionProgress as State} from "../../lib/plan/extractionProgress";

export function ExtractionProgress({state}: {state: State}) {
  return <div className="plan-extraction-progress" role="status">
    <span>{state.stage} · {state.percent}%</span>
    <progress aria-label="Plan analysis progress" value={state.percent} max={100}/>
  </div>;
}
