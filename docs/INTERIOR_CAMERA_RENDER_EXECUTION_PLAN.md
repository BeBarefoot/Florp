# Florp: measured interior camera and AI render experiment

The first experiment takes one confirmed, measured room from the existing
editor and produces a believable interior image from a viewpoint the user
can repeat. The PlanModel remains the source of truth. The rendered image
is a design preview; dimensions come from the model, not from the pixels
in the generated image.

## 0. Freeze the extraction checkpoint

Use the corrected second floor and its measurement reference for the first
experiment. Keep it as a separate saved revision. As a final check, extract
the original into a disposable project and verify the stored wall graph:
no leader extending above the top-left corner, and the bottom-middle
partition shares nodes at both ends. On `925d897` both checks passed through
the real extraction endpoint on the supplied source. If a fresh result
differs on the user's machine, compare the running API's commit, source
image hash, and saved revision. Do not block the camera work on another
round of extraction tuning.

## 1. Place and inspect a camera locally

**First slice:** in the scaled 3D view, click **Place camera**, click a room
floor for the position, then click another floor point to aim. **Preview
view** switches to a level perspective at an adjustable eye height
(default 1.60 m, vertical field of view 55°). **Back to orbit** returns to
the model. The marker is a camera position, not a person that will appear
in the render. The experiment does not edit the floor plan.

Next, add a 2D camera pin with a direction handle and frustum, named
viewpoints, pitch and FOV, and a fixed render-frame crop. Keep one aspect
ratio initially (4:3) and show it before capture. Validate that the camera
has floor and ceiling clearance, is outside walls, and starts in a closed
room. Block render submission until the scale is confirmed and the selected
view's walls and openings have been reviewed. Show which issue to fix.
Allow an explicitly reviewed room within an otherwise incomplete plan.

## 2. Save a reproducible shot

Create a revision-scoped shot record separate from geometry: plan and
revision IDs, model hash, scale reference, room ID, metric position and
orientation, vertical FOV, near/far planes, frame dimensions, and camera
intrinsics/extrinsics. The viewer, capture, and comparison view all read
that same record. Use the existing world convention: X/Z on the floor and
Y up. In perspective, convert vertical FOV and resolution to focal length
in pixels. Persist camera values at full precision. Editing a prompt
reuses the same shot; editing a wall makes a new revision and requires a
new capture rather than silently changing the old shot.

## 3. Capture geometry from the same camera

Build an offscreen render pass using the same wall pieces and opening
cuts as the 3D viewer. Complete the selected room's floor and ceiling
using reviewed heights. Add explicit frames, glazing masks and door
masks as needed; preserve window placement, size and sill height from
the approved model. Hide editor helpers and the orbit grid.

Save all passes at the same resolution and projection:

- A neutral lit render for visual comparison and image editing.
- Linear camera-space depth in metres, with an explicit invalid-pixel
  mask. Keep a high-precision master; produce the provider's normalized
  depth image separately with documented near/far mapping.
- A structural edge map and object masks for walls, floor, ceiling,
  doors and windows. Add normals only if the experiment benefits.

Before any provider call, overlay the passes and verify that all visible
corners and opening edges coincide. Use synthetic rooms of known size to
check projection, depth, window occlusion, frame orientation, resizing
and camera round trips. Do not infer missing geometry or scale from AI.

## 4. Run a narrow render comparison

Start with one room, one saved view, two prompts, and a short repeat run.
For example: “Warm oak floor, off-white walls, soft daylight; preserve the
opening positions and the camera.” Compare (a) the deterministic neutral
render, (b) an image edit conditioned on the render and its depth, and
(c) the same edit with an added structural mask or constrained regions.
Use the same framing and settings where possible. Do not send the
original floor-plan image; the neutral render and derived controls are
sufficient. Keep the local preview usable without any provider.

Implement a server-side adapter for one approved engine first. The current
legacy render route returns 501 and its queue adapter is not a complete
workflow. Confirm the engine's current inputs, output resolution, data
retention, model rights and cost before enabling it. Keep API keys in the
server environment. Make experimental submission explicit, with a per-run
budget and no automatic retries that can create a second paid job.

## 5. Reject renders that move the structure

Compare the image to the saved neutral view with a toggle and an overlay
of the projected opening outlines. Record missing/extra openings, corner
and opening edge displacement, and obvious furniture scale errors. For
the first test, require zero added or missing doors/windows and aim for
visible opening edges within 2% of the frame diagonal. Use manual review
when image edges are ambiguous. These are experiment gates, not a claim
of production accuracy. A depth-conditioned model can move structure;
if it does, constrain edits to material/furniture regions or render
materials directly on the metric geometry. Do not call an AI image
dimensionally accurate merely because it passed visual review.

## 6. Make the result repeatable and usable

Once one shot passes, save prompt variants and outputs under the same
shot. Add explicit queued/running/succeeded/failed states, duplicate
submission protection, safe polling and timeouts, and a thumbnail
comparison with the neutral render. Export the image plus the shot
metadata and originating revision. Add a small second-room trial before
expanding to multiple styles, mobile placement, or walkthroughs.

**Deliverables in order:** local eye-level preview → saved shot and
validated capture bundle → one opt-in AI render comparison → repeatable
prompt variants. The first slice ships no external AI call.
