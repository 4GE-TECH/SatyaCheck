# SatyaCheck frontend

<!-- impeccable:product-schema 1 -->

## Platform
web (web3/) with an Android companion (satyacheck_mobile/, Flutter) sharing one visual world.

## Users
Guardians checking suspicious recordings and enrolling family voices. Protected people need large, plain-language guidance under stress. Judges may read the dashboard from three metres away on a projector.

## Product Purpose
Explain a voice screening through identity, authenticity and intent, then help the person decide what to do next. A trust score is evidence, never proof of fraud or a guarantee of safety.

## Capabilities and Constraints
Existing local backend APIs only: POST /api/screen, GET /api/screen/{id}, /api/persons (list, delete), /api/enroll, /api/report/{id}/pdf, /api/health, and the /api/ws/screen/{id} live stream. No browser storage, remote fonts, new inference, model changes or frozen-contract changes.
Unknown speakers are neutral. Green appears only when a known voice is verifiable: an identity check whose match is not flagged as synthetic or replayed. A clone that matches a voiceprint is the attack, not reassurance. Insufficient audio has no displayed score. The backend confirms enrollment. Sample results are labelled everywhere. Android cannot hear a cellular call on the same handset: supported input is uploaded audio, a recorded clip, or live listening from a second device.

## Operating Context
Reports for the current session are held in memory with their audio, so a reopened report can redraw the real spectrogram; saved reports are retrieved by session ID without audio. No claim of on-device inference, encryption or persisted consent is made.

## Brand Commitments
Keep the SatyaCheck name and original logo. Do not copy the marketing site's palette. The user asked for a from-scratch, highest-craft build following the taste skills, with GSAP, and with original effects authored in the animation-template categories. The template sources were unavailable, so nothing claims to be them. Coordinated dark and light themes follow the system.

## Accessibility & Inclusion
Hindi, English and Hinglish content; large readable type (secondary text at least 14px); keyboard access; named controls; status announcements; reduced motion honoured with content visible by default; worded, non-colour status flags; no clipped evidence text.

## Evidence on Hand
PRD.md, CLAUDE.md, contracts.py and its TypeScript mirror, the scam-advisory corpus (nlp_rag/corpus/anchors/seed_anchors.yaml), three bundled demo clips, and six labelled mock fixtures. No commercial claims or fabricated user records.
