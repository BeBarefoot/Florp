import type {WheelEvent} from "react";

export function scrollTourRail(event: WheelEvent<HTMLElement>) {
  if (event.ctrlKey || event.shiftKey || event.deltaX || !event.deltaY) return;
  if (!(event.target instanceof Element) || event.target.closest("input,select")) return;
  const rail = event.target.closest<HTMLElement>(".tour-rail,.show-list");
  if (!rail || rail.scrollWidth <= rail.clientWidth) return;
  const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? rail.clientWidth : 1;
  rail.scrollLeft += event.deltaY * unit;
}
