# Florp phone app plan

Updated 23 November 2026 · [Issue #1](https://github.com/BeBarefoot/Florp/issues/1) · [Production gates](PRODUCTION_POC_PLAN.md)

The phone app serves buyers and homeowners who want to extract, walk through and adapt a home themselves. The Mac runs extraction and saves projects. The phone renders the shared 3D scene. Both use the same plan and scene revisions.

## Current flow

The PWA has a project library, camera and multi-file upload, and a tour that opens directly from the web editor. It supports touch movement, dollhouse floor landing and saved stops. The phone tour offers an approximate draft before calibration. **Edit floor** opens the shared plan editor. When the draft has no closed rooms, **Mark a walkable floor in the editor** guides the buyer through drawing a floor area and placing a camera.

See [installation and private HTTPS setup](../README.md#run-and-install-the-smartphone-app). Validate the complete journey on physical iOS and Android devices. Compact phone repair tools and the chat assistant are planned below.

## The phone experience

| Screen | What the user does | What Florp does |
| --- | --- | --- |
| Upload | Take a photo, pick an image/PDF, or add a second floor. | Show an oriented preview and allow retake or crop. Run existing local extraction and show progress. Open a draft walkthrough as soon as geometry is ready. Label assumed scale and offer a two-point measurement with a magnified touch target. Put uncertain doors and windows in a short review sheet. For two images, suggest the floor order and ask the user to confirm it. |
| Walk | Tap a room to start, drag to look, then tap a reachable spot to move. | Render the same PlanModel wall pieces, openings, rooms and furniture in Three.js. Use standing eye height and reject a direct move whose path crosses a solid wall, closed door or furniture. If a path is blocked, keep the camera in place and explain how to reach the room. Provide a floor switcher and show reviewed garden/stair outlines in the plan overview. |
| Design | Tap **Design this view**, type a prompt or start from a preset, and compare the result with the scene. | Save the current camera and frame, then capture RGB, depth and object IDs from that pose. Offer instant floor swatches and local AI generation as distinct actions. Show the captured frame immediately while generation runs, retain the job on reload, and show before/after with the same framing. A user can target a visible object with the existing local crop workflow. |

## Buying a home before it’s built

The buyer has a floor plan for a house they’re considering and wants to see how
it could feel furnished. Success means they can walk through a version with the
finishes they chose and see whether their furniture fits at real scale. Reuse
the upload, plan editor and walkthrough that already work. Design the new screens
around the decisions below.

| Screen | What the buyer sees and does |
| --- | --- |
| **Upload and walkthrough** | Upload a PDF, photo or plan image, then open the 3D draft as soon as it’s ready. Offer a focused review when Florp flags a missing wall, an opening, or a room without a floor. Let the buyer check the drawing beside the 3D draft and confirm one known measurement before making fit decisions. |
| **Start designing** | From the walkthrough, choose a starter palette such as *Warm wood*, *Light and neutral*, or *Modern concrete*, start from scratch, or open **Ask Designer** when available. Show a preview of the starter finishes and make each choice editable. Chat can ask about preferred colours, upkeep, or rooms that need a different finish, then preview its proposed choices in the same controls. |
| **Floors and walls** | Open a sheet over the 3D view. Pick **Floor** or **Wall**, then a room or group, such as the main living area, kitchen, bedrooms, or bathrooms. Choose wood, concrete, marble, or tile for floors. Show colour, finish and tile or plank dimensions when applicable. For walls, offer paint colours and finishes such as tile. Preview at actual pattern scale in the current view, and tap a surface to switch scope. Let buyers apply a finish to one room, a group, or the whole home, and select an individual wall for an accent. Keep room overrides visible so users can see what will change before applying a palette. |
| **Furnish** | Open a catalog of objects at real scale. Show dimensions before placement. On a phone, select an item and tap the floor to place it. On desktop, also support dragging it from the catalog. Move and rotate furniture in 3D, or switch to the 2D plan for precision. Flag an overlap, a blocked door swing, or a tight walkway with the affected area highlighted. Offer size entry for an item the buyer already owns. |
| **Walk through and compare** | Return to the walkthrough with the chosen materials and furniture. Compare a saved alternative from the same viewpoint, then save the preferred version. Reopen it later with the same room finishes and object dimensions and positions. |

Keep the 3D view visible during editing. Use three persistent actions after
upload — **Walk**, **Finishes**, and **Furnish** — with room selection and the
current scope shown in each edit sheet. Give chat the room or surface the buyer
has selected so it can ask a specific question and show a proposal for approval.
The planned Pro Designer also handles layout requests that need structural
constraints and a named variant. [Designer workflow](ROADMAP_ACCURACY_MOBILE.md#designer-workflow)

### First prototype

Reuse a working four-room plan. Take it from the upload confirmation to the
walkthrough, then let the buyer apply oak to the main area, use a different
kitchen floor, change the bathroom tile size and colour, paint a bedroom wall,
and place a sofa and bed. Verify that the kitchen and bathroom keep their own
finishes after a whole-home palette change unless the buyer chooses to replace
those overrides. Confirm that the bed keeps its dimensions when moved or
rotated, that a blocked door is visible in the placement controls, and that all
choices survive reopening the design.

Build room-level floors and wall finishes first, then the catalog and placement
controls. The preset path gives the prototype a complete journey. Add the chat
entry point to the design prototype and connect it to those same finish and
furniture actions when the Pro assistant is ready.

## Self-serve repair

Keep the original drawing visible and take the buyer to the specific problem. Prioritize a wrong scale, a missing wall, an unclosed room, and misplaced doors or windows. Use the same revision checks and geometry operations as the shared editor. Show the effect in 2D and 3D and provide undo. A marked walkable floor lets the buyer continue while resolving missing architecture.

For the planned chat assistant, start with one selected finding or region at a time. Propose a specific edit using source evidence, ask for a measurement or target when ambiguous, and show the change before the buyer applies it. Record accepted repairs in plan history. Keep building edits separate from optional image generation.

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
| 4. Owner pilot | Run the flow on the user's phone with a known-scale single floor and a paired property. | Track upload-to-draft, buyer correction time, time to first usable design and repeat edits separately. Use issue #1's held-out accuracy gate before counting the flow as trusted. |

Proposed budgets to verify on hardware: a first editable draft within two minutes at P90 on supported clean plans, at least 30 FPS while walking on each tested phone, and a warm local AI preview within three minutes at P90. Record failure rates and sample sizes. The first implementation can use synthetic plans and mocked generation. Real drawings, an actual phone session and a live local ComfyUI run establish accuracy and responsiveness for the owner pilot.
