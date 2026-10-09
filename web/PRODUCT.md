# SatyaCheck frontend

<!-- impeccable:product-schema 1 -->

## Platform
web

## Users
Guardians checking suspicious recordings and enrolling family voices. Protected people need large, plain-language guidance under stress. Confirmed by PRD.md and the frontend-overhaul brief.

## Product Purpose
Explain a voice screening through identity, authenticity, and intent, then help the user decide what to do next. A trust score is evidence, never proof of fraud or a guarantee of safety.

## Capabilities and Constraints
Use the existing React/TypeScript application and existing local backend APIs. No browser storage, remote fonts, new inference, model changes, or frozen-contract changes. Unknown speakers are neutral; authority-check mode never displays verified green. Insufficient audio has no displayed score. The backend confirms enrollment. Sample results must be explicitly labeled. Android cannot hear a cellular call on the same handset: supported input is uploaded audio or recording on a separate device.

## Operating Context
The web workspace supports screening, known voices, and session-linked reports. Recent checks are held in memory for the current open page; the API exposes retrieval by ID but no history-list endpoint. No claim of on-device inference, encryption, or persisted consent is made.

## Brand Commitments
User approved a calm, readable, evidence-led replacement; coordinated light and dark themes; native Flutter Android companion; code-first implementation. Keep the SatyaCheck name. The user subsequently delegated critical design decisions and approved a professional startup entry with purposeful 3D, pulse and hover motion, while retaining the clinical report system and existing screening capabilities.

## Accessibility & Inclusion
Hindi, English and Hinglish content; large readable type, keyboard access, named controls, status announcements, reduced motion, and non-color status labels.

## Evidence on Hand
PRD.md, AGENTS.md, PLAN.md, existing API contracts, real enrollment/screen/report endpoints and six explicitly labeled web sample fixtures. No commercial claims or fabricated user records.

Brand update (2026-10-08): retain the user's supplied logo as a locally bundled asset. The user-selected cool clinical laboratory-report world supersedes the original warm-ivory marketing inspiration: indigo letterhead, cool report paper, Manrope and coordinated light/dark evidence states.

Motion update (2026-10-08): the dark indigo introduction uses a locally modeled, pausable voice shield as a brand illustration. Its fixed waveform is not audio measurement; reduced motion keeps it static and unavailable graphics use a shield fallback. This extends the existing workspace rather than adding a marketing site or new product features.

Design update (9 October 2026): the user authorized a fresh frontend. The Clarity workspace in DESIGN.md supersedes the indigo letterhead and pausable WebGL introduction described above. It uses graphite navigation, silver surfaces, coral actions, a finite decorative acoustic-ribbon entrance and persistent mobile navigation. Existing branding, APIs and evidence semantics remain. The previous native Flutter work is outside this task.
