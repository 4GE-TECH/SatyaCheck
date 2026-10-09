---
version: 1
slug: "src-app-tsx"
primary_target: "src/App.tsx"
related_targets: []
---

# Screening workspace

Operate mode. A guardian checks a recording (upload, nearby recording, or live listening from a bystanding device), reads a report of evidence, manages known voices, and keeps session reports. Judges may read it from three metres on a projector.

## Direction contract
THESIS: The verdict is a signed laboratory report. Every finding is an observed value set against its reference interval, flagged, and cited. It refuses the category default of a score dial, a hero metric and equal cards.
OWN-WORLD: Pathology report grammar in a cool clinical palette. Deep indigo letterhead band carries the logo and navigation. The page is cool white, with report sheets bounded by hairlines. Results tables use Test, Result, Reference and Flag columns with tabular numerals; reference-interval bars have tinted zones and a value tick. Flags are H, L or OK, and verdict colours appear only in flags and bands. Electric indigo is reserved for actions. Manrope carries everything; IDs use the system mono.
STORY: Requisition (choose audio), processing, then the report: interpretation first, the results table, remarks with citations, a transcript with highlighted phrases, then next steps. Live listening is a provisional report that updates in place and becomes final when listening stops. Insufficient audio is reported as QNS (quantity not sufficient), with no score.
FIRST VIEWPORT: Letterhead navigation bar across the top (brand, Check, Known voices, Reports, Help, service status, theme). Left: a requisition panel with Upload, Record and Live tabs plus the primary action. Right: "What the report measures", three test rows with their reference meaning. Below: a table of reports from this session. Signature move: reference-interval rows, which update in place when listening live.
FORM: Pathology lab report, rank 1 on my grounded list (IMPECCABLE'S PICK), user-chosen over assigned slot 7. Seed a42fa08d. Raises: numeric value and threshold on every row (exposure record); strict column grid (Crouwel); one next-step band (airport wayfinding); the audio playhead drives the authenticity strip (j-card).
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## User-authorized brand and motion extension (2026-10-08)

The user delegated critical design decisions and requested a professional startup presence with 3D, smooth effects, pulses and hover feedback. Extend the existing screening workspace with a dark indigo introduction and an actual locally modeled WebGL voice shield. Three orbital paths explain the three signals; the model is a brand illustration, never a displayed measurement. Keep the ruled evidence reports and their truth states.

FIRST VIEWPORT UPDATE: compact letterhead, then a two-column introduction: clear heading and direct check/enrollment actions on the left, pearl/indigo 3D shield and named signals on the right. The input task remains immediately below. On phones the model follows the text. No splash screen or animation delays access to the task.

MOTION THESIS: the authored moment is the shield's subtle physical turn, with pointer response on precise pointing devices. Continuity uses short, interruptible control transitions; hover acknowledges actionable upload/link/button states. Pulse only the explanatory signal points and actual recording/connection activity. The 3D renderer is lazy-loaded, caps drawing at 30fps and DPR at 1.5, pauses offscreen/hidden, has a visible pause control, and becomes a static model under reduced motion. A static shield replaces it if WebGL fails. No new inference, runtime external request, or score animation is introduced.
