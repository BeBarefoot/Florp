# Florp phone app plan

21 November 2026 · Phone experience for [issue #1](https://github.com/BeBarefoot/Florp/issues/1) · [Production POC](PRODUCTION_POC_PLAN.md)

Build an installable web app with three screens: **Upload → Walk → Design**. The phone handles touch, local 3D display and camera capture. Florp on the user's M5 Mac runs plan extraction, saves projects and optionally runs local ComfyUI. Reuse the existing Next.js app and FastAPI engine so the phone and desktop editors work on the same project and revisions.

## The phone experience

| Screen | What the user does | What Florp does |
| --- | --- | --- |
| Upload | Take a photo, pick an image/PDF, or add a second floor. | Show an oriented preview and allow retake or crop. Run existing local extraction and show progress. Open a draft walkthrough as soon as geometry is ready. Label assumed scale and offer a two-point measurement with a magnified touch target. Put uncertain doors and windows in a short review sheet. For two images, suggest the floor order and ask the user to confirm it. |
| Walk | Tap a room to start, drag to look, then tap a reachable spot to move. | Render the same PlanModel wall pieces, openings, rooms and furniture in Three.js. Use standing eye height and reject a direct move whose path crosses a solid wall, closed door or furniture. If a path is blocked, keep the camera in place and explain how to reach the room. Provide a floor switcher and show reviewed garden/stair outlines in the plan overview. |
| Design | Tap **Design this view**, type a prompt or start from a preset, and compare the result with the scene. | Save the current camera and frame, then capture RGB, depth and object IDs from that pose. Offer instant floor swatches and local AI generation as distinct actions. Show the captured frame immediately while generation runs, retain the job on reload, and show before/after with the same framing. A user can target a visible object with the existing local crop workflow. |

The main journey has one primary action per screen. Keep the plan editor available through **Review plan** for corrections. Use an explicit draft label for approximate walkthroughs and unlock calibrated camera capture after scale confirmation. Architectural acceptance stays tied to the saved plan revision. In the first release, prompts create visual designs. Furniture placement and edits to the model use explicit controls and the existing scene/plan commands. Two floors are separate walkthroughs with a floor switcher. Continuous stairs require calibrated alignment, matching landings and floor elevations.

## How to keep it slim

- Add a phone-specific route inside Next.js. Share API calls, PlanModel, scene commands, wall meshes, camera math and capture code. Split out the desktop editor and load the 3D code only when entering Walk. Use thumbnails for browsing and original-resolution sources for extraction.
- Keep the 3D view responsive with capped device pixel ratio, reused geometry/materials and one canvas. Capture a full-size provider frame only when requested. Profile actual devices before adding heavier assets, codecs or effects. Test recovery from WebGL context loss and CPU/GPU pressure.
- Keep the install manifest, icon and static shell small. Project access and generation require a connection to the Mac for the first release. Persist acknowledged edits through the existing revision APIs. Show disconnected or unsaved states explicitly. Resume status reads on reconnect and reuse the existing render request key when retrying the same submission.
- Add a same-origin authenticated HTTPS entry point for the owner's phone on a private network. Proxy only the required app/API routes to loopback, keep ComfyUI and its credentials on the Mac, and verify project access on the server. The phone connects to the Mac's private HTTPS address. Phone localhost refers to the phone. Access is available while the Mac is awake and Florp is running. Hosted pilots follow production gate F.

## Build order and acceptance

| Step | Deliverable | Acceptance |
| --- | --- | --- |
| 1. Phone shell and upload | Project picker, camera/photo-library/file controls, two-image upload and status. Add install manifest and private HTTPS entry point before opening access from a phone. | On iOS Safari and Android Chrome, upload portrait and landscape photos and a PDF, recover from a permission denial through the file picker, and reopen a saved pair. Verify unauthenticated calls are rejected and both original upload and saved edits survive disconnects. |
| 2. Walk and review | Touch camera controls, room spawn points, collision-aware tap-to-move, floor switcher and compact scale/opening review. | In a two-room test scene, walk through an open door and stop at the same door when closed. Preserve camera on rotation and return to the session after backgrounding. Check 360 and 390 px widths, 44 px touch targets, and actual device performance. |
| 3. Design from here | Save pose, capture frame, prompt, presets, generation status and comparison. Keep existing review and provider consent semantics. | Same view and geometry after reload, one submission per intent, clear recovery when ComfyUI is unavailable, and repeatable camera alignment in preview and export. Measure selected-object and whole-view output quality and latency on the Mac. |
| 4. Owner pilot | Run the flow on the user's phone with a known-scale single floor and a paired property. | Track upload-to-draft, human review time, time to first usable design and repeat edits separately. Use issue #1's held-out accuracy gate before counting the flow as trusted. |

Proposed budgets to verify on hardware: a first editable draft within two minutes at P90 on supported clean plans, at least 30 FPS while walking on each tested phone, and a warm local AI preview within three minutes at P90. Record failure rates and sample sizes. The first implementation can use synthetic plans and mocked generation. Real drawings, an actual phone session and a live local ComfyUI run establish accuracy and responsiveness for the owner pilot.
