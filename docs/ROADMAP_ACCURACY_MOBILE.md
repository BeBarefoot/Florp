# Accuracy-first mobile roadmap

Updated 23 November 2026. This is the entry point linked from
[issue #1](https://github.com/BeBarefoot/Florp/issues/1).

The authoritative work packages, target metrics, prerequisites, owner roles and
release evidence now live in [Production POC delivery plan](PRODUCTION_POC_PLAN.md).
The [architecture audit](ARCHITECTURE.md) distinguishes implemented features from
unverified product claims. Earlier roadmap versions remain in Git history.

1. A: Reproducible setup and supported-input contract.
2. B: Gate 1 — held-out extraction/fixture benchmarks and correction-time evidence.
3. C: Revision-specific verification, calibration and 2D/3D/export parity.
4. D: Mobile-first guided review, PWA and real-device usability.
5. E: Authorized live provider validation and output structural consistency.
6. F: Authentication, authorization, durable jobs, backup/restore and hosted pilot.

The product goal is self-serve use. A buyer should get the most accurate draft the source supports, walk through it, and repair uncertain geometry using phone controls or a suggestion from the planned Pro chat assistant that the buyer can approve.

**Next milestone.** Benchmark automatic extraction on independently annotated plans. Measure walls, openings, room closure, scale, and the share of buyers who reach a usable tour unaided within five minutes of corrections. Tackle the largest failure categories first and validate the repair flow on real phones. Independent annotations provide benchmark ground truth. Buyer approval records corrections in the app.

The shared geometry, saved cameras, phone tour, floor recovery, capture and render flow are implemented. Real-plan accuracy, phone repair usability and hosted readiness remain open release gates.


## First buyer experience

Start app design with the journey for someone buying an unbuilt home. The buyer
uploads a floor plan, corrects what needs attention, walks through the model,
chooses floors and walls by room, then places furniture at real scale. Give the
buyer an editable starter palette and a planned Designer chat entry point that
works with the same finish and furniture controls. [First buyer experience](PHONE_APP_PLAN.md#buying-a-home-before-its-built)

## Product tiers and site placement

The four product pillars guide both tiers. Convert 2D plans into editable 3D homes,
walk through them at a calibrated scale, generate realistic AI previews from saved
views, and place objects using their real dimensions. Keep manual plan corrections
available in the core app.

### Build the Pro foundations from day one

Use the same versioned plan and scene in both tiers, with stable IDs, metric units,
saved cameras, and asset references. Check feature access on the server so Pro
modules can be enabled per account. Provide a common job interface for rendering
and AI work that records the input revision, progress, failures, retries, and
usage. Keep provider credentials on the server. These foundations let each module
ship independently as it clears validation.

| Planned Pro feature | Scope and release evidence |
| --- | --- |
| AI chat assistant | Let users point to a room, wall, or object and ask for a repair. Add a [Designer workflow](#designer-workflow) for layout goals that need questions and options before editing. |
| Unreal Engine graphics | Prototype an Unreal Engine renderer for higher-quality lighting, materials, and furnished interiors. Verify scale, openings, object placement, and camera framing against the same Florp scene. Compare still renders and streamed walkthroughs using phone performance, loading time, and GPU cost per session. |
| Advanced modules | Start with whole-home tools such as multi-floor editing and design variants. Use the same plan and scene contracts so edits and exports retain real-world scale. |
| Pro support | Add a support entry point from the project. Let the buyer choose which diagnostics, plan, or scene to share. Define the support channel and response targets before launch. |

### Designer workflow

Start with a walk-in closet in a four-room home as the first end-to-end Pro
design task. In the plan editor or phone walkthrough, the buyer opens **Designer**,
selects the bedroom or adjoining area, and describes the goal in their own words.
Designer uses the calibrated plan and existing furniture dimensions to ask targeted
questions and show which wall, wardrobe, or door it means.

1. **Establish what can move.** Ask which room should get the closet, whether all
   four rooms must remain, and how much storage the buyer needs. Ask whether the
   freestanding wardrobe can move, whether the bedroom door can move or change
   swing, and what is known about the target wall. Record wall material (such as
   brick or block) and load-bearing status independently. Offer **I’m not sure**
   and keep load-bearing and unverified walls fixed in editable proposals. When
   the buyer is unsure about the wall or doorway, offer a layout using furniture
   or new partitions that respects those constraints.
2. **Compare measured options.** Show alternatives in 2D and in the walkthrough.
   For each option, show wardrobe depth, usable storage, aisle width, door swing,
   remaining bedroom area, and any trade-offs. Confirm missing measurements that
   affect fit and check the route from the bedroom into the closet. Show any
   proposed moves or replacements directly on the plan.
3. **Apply and export.** Let the buyer approve one proposal as a named design
   variant. Validate room boundaries, wall and door constraints, clearances,
   metric scale, and the source revision before applying the edits. Keep the
   original available for comparison and allow undo. Export the selected variant
   as an editable Florp ZIP, 2D plan, and 3D GLB, with the same geometry and scale
   across all outputs.

The first release should demonstrate the complete four-room workflow with a
movable wardrobe, a fixed door, and an unverified wall. A second test should allow
an explicitly movable doorway and show the difference in clearance. Verify that
the approved variant reopens from its Florp bundle and matches the 2D drawing
and 3D export.

### Place the model at its real address

1. Enter an address and use Google Maps Platform geocoding to find it. Confirm the building on the map and move the pin to the correct footprint if the address result lands at the entrance or parcel center.
2. Preview the calibrated 3D model at that location. Adjust its position, compass heading, and elevation. For an apartment, let the buyer specify which level the model belongs to. Save the placement with the project so it can be reopened and adjusted.
3. Validate map rendering on phones. Check how Google Maps 3D handles Florp model overlays, terrain and existing buildings, and supported browsers. Test the saved placement on houses, apartment buildings, ambiguous addresses, and locations with limited 3D coverage. Use a 2D map with the footprint and a link to the walkthrough where the 3D placement view is unavailable.

Store the geographic placement separately from local plan coordinates so moving or
rotating the map overlay preserves all room and object dimensions. Treat the
address and exact coordinates as private project data. Confirm Google Maps
coverage, usage costs, and terms for address data and 3D map content before
release. Decide tier access for map placement after that pilot.
