# SatyaCheck — Clarity workspace

Current design direction, 9 October 2026. This replaces the earlier indigo letterhead and WebGL introduction. The user authorized a fresh frontend on `frontend-overhaul`; implementation stays in `web/`.

## Product and composition

A guardian needs to check audio, understand the evidence, and decide what to do next. The interface is a working safety tool, not a promotional landing page. The principal screen places audio input beside three short signal explanations. Known voices, reports, and guidance share the same navigation and surface system.

The signature is a fine coral acoustic ribbon. It suggests listening without pretending to show a measured waveform. It is deterministic SVG, hidden from assistive technology, bundled with the app, and independent of microphone state. The existing supplied SatyaCheck logo remains intact.

Desktop: 232px graphite sidebar, 78px breadcrumb bar, 40px main inset. Below 1200px the sidebar narrows to 200px. Below 760px it becomes a compact header with four persistent bottom navigation destinations. The checking screen collapses to one column at 1000px. Safe-area insets and extra footer clearance protect the mobile dock.

## Color and type

| Role | Light | Dark |
| --- | --- | --- |
| Page | `#f4f5f3` | `#171c1a` |
| Surface | `#ffffff` | `#202724` |
| Secondary surface | `#f8f9f7` | `#262f2a` |
| Main text | `#232a28` | `#eef2ec` |
| Supporting text | `#4e5753` | `#c4cec6` |
| Muted text | `#66706b` | `#a5b1a7` |
| Divider | `#e3e7e1` | `#354038` |
| Navigation | `#202725` | `#121815` |
| Link / focus | `#984733` | `#eda38b` |
| Action fill | `#edac91` | `#edac91` |
| Action text | `#352019` | `#352019` |
| Decorative ribbon | `#de866c` | `#de866c` |

Result colors remain separate semantic tokens: green for verified identity, amber for caution, red for concerning evidence, neutral for unknown or insufficient. Coral is an interaction color, not a result band. Print uses the established high-contrast semantic palette on white.

Locally bundled Manrope serves display and body roles. Display uses 650 weight, tight tracking and 1.09 line height; the main heading scales from 32px on small phones to 60px on large screens. Body and form typography use a 16px base. Identifiers use the existing system monospace stack. Hindi uses system Devanagari fallbacks. No remote font request is needed.

## Components

- Main surfaces have 22px corners (18px on phones), quiet borders, and restrained shadows. Secondary containers use 12–16px corners. Buttons are pills with at least 44px targets.
- Navigation uses icons plus text and `aria-current`. Selected mobile destinations remain legible in both themes. No icon is the sole indication of the current route.
- Recording and live listening share a segmented track. A translated surface follows the active tab. Keyboard arrow/Home/End support and roving focus are retained.
- File upload and recording are explicit alternatives inside the selected source. Upload is the first enabled primary action. The check action becomes available after selecting audio.
- Reports keep immediately visible actual values, quality gates, three independent signals, synthetic-run statistics, transcript markers, cited reason codes and next steps. Charts never animate through invented intermediate scores.
- Enrollment keeps consent, multilingual prompts, service-confirmed voiceprints, retry and removal recovery. Names wrap; avatars retain complete Hindi and emoji graphemes.
- Reports this session are held in memory. No browser storage, fabricated history, or new persistence behavior is introduced.

## Motion contract

Use `--ease-out: cubic-bezier(0.23, 1, 0.32, 1)`. Controls use 120ms press feedback; color and border feedback use 160–180ms; the source-tab indicator translates in 220ms. Route entry fades and rises 5px over 240ms. Route changes scroll to the top and focus the main region.

The acoustic illustration has a one-time 900ms entrance; it settles and needs no pause control. No WebGL runtime or continuous decorative render loop is loaded. Its motion is optional and disabled under reduced motion. Precise-pointer hover enhancements are capability-gated. Motion never delays access to a control. Existing activity indicators are reserved for actual connecting, recording or processing states.

Do not add scroll hijacking, perpetual marquees, animated numerical verdicts, moving warning copy, fake live measurements, or new motion libraries for these simple interactions.

## Product invariants

Unknown identity remains neutral. Authority checks cannot be green. Insufficient speech has no score. Synthetic speech alone does not determine fraud. Sample results remain explicitly labelled. A phone in a cellular call cannot capture that call through this app; live listening explains the second-device requirement. Backend contracts and model behavior are unchanged.

## Verification

Build, lint, 10 unit tests and 22 browser tests pass. Browser coverage includes all six sample bands, actual request-shaped failures, enrollment consent, empty voiceprints, long Hindi/Latin names, grapheme avatars, 320/390/768/1440px layouts, 200% text, desktop/mobile themes, keyboard tabs, navigation, reduced motion, no-WebGL availability, long report evidence, print colors, and WebSocket finalization/interruption.

The browser suite uses intercepted API fixtures, not live model inference. Physical phones and real microphone acoustics were not validated. Screenshots are in `.impeccable/review/`; the generated visual reference and its prompt are in `design-reference/`.
