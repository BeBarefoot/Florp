# Deterministic service validation — 2026-10-29

This opt-in service is a tested color extraction baseline; it does not replace Florp's main editor. No claim of production extraction accuracy or a universal timing guarantee is made.

## Timing

Measured on Intel Xeon Platinum 8573C, x86_64 Linux, Python 3.12.14. The host exposes nine CPU cores; the benchmark and child workers were pinned to **eight** (0–7). Tesseract/OpenMP and BLAS used one thread; OpenCV allowed eight. Five warm and five fresh-worker HTTP requests were measured per image/OCR configuration (30 fresh-worker HTTP requests total). All completed without HTTP errors.

Times include image decoding, preprocessing, local OCR when enabled, calibration, masks, vectors, layer classification, 300 DPI PNG rendering, SVG/DXF encoding and ZIP encoding. Fresh-worker HTTP timings also include Python/native dependency startup, temporary file I/O and local HTTP multipart dispatch/response; no network transfer. Inputs are one synthetic 2400×1600 color plan and the two supplied original scans (1306×408 and 992×440). Source hashes/dimensions are in the JSON. No originals are committed.

| Input | OCR | First direct (s) | Warm maximum (s) | Fresh-worker HTTP maximum (s) | Errors |
| --- | --- | ---: | ---: | ---: | ---: |
| synthetic_2400x1600 | Off | 1.243 | 1.068 | 2.083 | 0 |
| synthetic_2400x1600 | On | 1.347 | 1.764 | 2.699 | 0 |
| Screenshot 2026-10-24 at 21.51.52.png | Off | 0.346 | 0.410 | 0.868 | 0 |
| Screenshot 2026-10-24 at 21.51.52.png | On | 0.773 | 1.043 | 1.265 | 0 |
| Screenshot 2026-10-25 at 8.28.17.png | Off | 0.230 | 0.271 | 0.672 | 0 |
| Screenshot 2026-10-25 at 8.28.17.png | On | 1.004 | 1.160 | 2.011 | 0 |

All recorded values in the separate benchmark are below **3.5 seconds**; the slowest fresh-worker request was **2.699 seconds**. The default 4.8-second deadline is enforced by killing the process group, not by returning partial geometry. One active plan is admitted per service process; additional requests receive 429. This is a measured fixture result on this host, not a guarantee for arbitrary images, different Macs, process scheduling or concurrent workloads.

`benchmark.json` contains every timing, stage timing, HTTP failure list, options-related warnings and hardware metadata. `benchmark-initial-contended.json` preserves the **failed first attempt**, run concurrently with the full regression suite before the final faded-ink filtering. Its first direct synthetic extraction took **5.464 seconds**; warm/isolated requests passed. This demonstrates why CPU isolation and the timeout policy matter. It has not been hidden or counted as a passing run.

Tesseract `eng` was installed; `heb` was **not installed** on this host. OCR completed with the installed language and reported the missing Hebrew model. Hebrew inference latency/accuracy therefore remains unmeasured; the supplied container installs both models. Benchmark requests explicitly allowed a default scale of 1px/cm so OCR ambiguity could not turn this into an empty-output timing benchmark. That assumed scale is not a measurement of the real plans.

## Verification

- 29 dedicated tests cover exact 50cm vector margins (including 0.73, 1.37 and 2.5137px/cm scales), hierarchy/holes/islands, opening preservation, faded hatching, material overlap, outer-only mode, cropped perimeter rejection, snapping/diagonal preservation, source-reference transforms, true-aspect perspective transforms, Canny/Hough page detection, numeric witness consensus, missing calibration, invalid source/ROI, output allocation limits, alpha handling, deterministic artifacts, local OCR timeout/fallback, HTTP validation, worker cancellation and 429 admission.
- The 50cm margin tests assert all **four** architecture-to-viewport distances in centimeters. They do not merely check a reported field. PNG embeds 300 DPI at explicit drawing scale; SVG and DXF contain the required named layers and units.
- Independent DXF QA using **ezdxf 1.4.5** loaded exports for both original scans: millimeter units, closed curves, **zero audit errors and zero automatic fixes**. The first QA found a missing layer-table handle; this was corrected before release. ezdxf is a QA dependency only, not part of runtime.
- Full backend regression: **278 tests passed** in 15.19 seconds, with one existing Starlette/httpx deprecation warning. CI results are recorded in the PR.
- Docker was unavailable locally, so the provided Dockerfile was not built. Local FastAPI subprocess execution is tested directly. Existing web/editor code is unchanged.

## Real-plan limitations found, not just hypothetical risks

The cropped ground-floor scan has an unresolved exterior under this pipeline; it exports material evidence with block walls explicitly unclassified. The upper-floor scan can produce provisional exterior/interior labels, but its faint hatching remains fragmented in places. Red dimension/elevation strokes can survive color filtering. A cleaner generated reference is not geometric ground truth. No per-pixel manually traced architectural reference was provided, so there is no real-plan IoU/recall or centimeter-error result to report.

A separate exploratory run used 0.55px/cm to inspect fading at a plausible drawing sampling scale; that number was explicitly assumed, not verified. It is not used as an accuracy assertion. Output reports always identify scale source, processing transforms and `requires_review=true` / `accuracy_certified=false`.

Correct margin math and a fast, deterministic engine do **not** establish complete wall recognition. These limitations are why the service remains opt-in rather than silently replacing a previously working extraction path. See the service README for the exact operational contract and independent evaluation criteria.

## Primary implementation references

- OpenCV contour hierarchy and structural analysis: https://docs.opencv.org/4.5.4/d3/dc0/group__imgproc__shape.html
- Shapely topology-preserving simplification: https://shapely.readthedocs.io/en/2.1.2/reference/shapely.simplify.html
- Local Tesseract languages/install: https://tesseract-ocr.github.io/tessdoc/Installation.html
- DXF LWPOLYLINE specification: https://help.autodesk.com/view/OARX/2024/ENU/?guid=GUID-748FC305-F3F2-4F74-825A-61F04D757A50
