# Extraction crop regression correction

The dominant-band envelope override introduced in PR #23 could select only the upper-right group of rooms and discard the remaining building. It has been removed. The earlier closed-envelope method is retained, with a guard: an inferred outline that discards more than 5% of detected structural pixels is not applied. A user-drawn outline is still authoritative. This favors retaining geometry over aggressively filtering site context when the boundary is uncertain.

Junction projection and ink-supported extension now reject destinations outside the image; extension also rejects collapsed segments. These prevent invalid generated coordinates from invalidating the complete worker document. The monochrome fallback respects the selected outline. Pale-hatch rectangle coordinates are converted to native Python integers at the OpenCV boundary.

Previously every nonzero worker exit was reported as HTTP 422 with a misleading image-quality message, and stderr was discarded. Worker failures now record the actual traceback in API logs and report HTTP 500 without replacing saved geometry. The exact cause of the user's reported worker exit cannot be established from the old generic message alone.

No tests, builds, extraction runs or browser checks were executed for this correction, at the user's request. CI is skipped for this change. Visual restoration and the reported failing photograph remain for the user's manual evaluation.

Pull main, restart the API and web app, and use **Re-extract from drawing**. Opening an existing saved revision does not recompute extraction. If the worker still fails, its API traceback now identifies the underlying exception.
