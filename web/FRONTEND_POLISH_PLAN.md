# Dashboard polish plan

Date: 2026-10-09. Execution branch: `frontend-overhaul`. Only `web/` may change. No commits or pushes.

## Design decision

Preserve the approved startup introduction and clinical evidence reports: locally bundled Manrope, indigo letterhead, cool paper, a pausable 3D shield, compact trust readout and ruled signal rows. This is a refinement of the shipped direction. Measured evidence remains calm, immediately readable and independent of decorative motion.

## Skill use

Impeccable governs bounded polish and hardening. Animate, Apple Design and Emil Design Engineering guide immediate feedback and interruptible, inexpensive motion; Review Animations checks the result. Break UI supplies realistic adversarial data through test API fixtures. Mobile Native and UI/UX Pro Max guide touch targets, hover capabilities, zoom and safe areas. Frontend Design and the taste skills inform restraint within the incumbent visual system.

The other selected skills are checked for applicability: animation vocabulary names effects when needed; Find Animation Opportunities and Improve Animations supply audit guidance; Pick UI Library favors existing native controls and no new dependency. Expo, Swift, mobile image concepts, web image concepts and Google Stitch do not require implementation here: this is an existing React web dashboard with approved local art and a design system, not a native app, new image commission or Stitch build. The v1 taste skill is supplementary to the current version. Repository ownership and the user's brief take priority over conflicting defaults.

## Execution order

1. **Protect the workspace.** Confirm branch, record branch references and existing modifications outside web, and inspect current source and review evidence. Recheck these at completion.
2. **Polish the interaction layer.** Make compact controls at least 44px, add immediate press feedback and touch manipulation, gate hover by pointer capability, keep pinch zoom and selectable report text, accommodate screen safe areas, and keep focus visible around the sticky header. Preserve form content and product claims.
3. **Harden realistic content and motion.** Test known voices with long Hindi/Latin names, combining characters, emoji, missing optional metadata and long relationships. Wrap identity text rather than conceal it; keep avatars and actions stable. Test long report evidence and transcript data. Move signal/timeline updates from animated layout properties to transforms without changing their measured positions. Keep concurrent known-voice actions consistent while a deletion is pending.
4. **Verify and document.** Run build, lint, unit and browser checks; cover 320/390/768/1440px, enlarged text, both themes, reduced motion, keyboard use, service failures and long data. Capture desktop/mobile together, apply any material findings in one batch, then confirm once. Update design documentation from the final source and record the results.

## Evidence and acceptance

- Current source has 34px connection/tab controls, 38px icon controls, 28px language switches and a 32px model control. Acceptance: these remain legible and actionable with at least 44px control height.
- Global hover styles currently apply without capability gating. Acceptance: hover enhancement requires `(hover: hover) and (pointer: fine)`; focus and press feedback work independently.
- The viewport does not opt into safe-area coverage. Acceptance: safe-area-aware shell spacing, without disabling browser zoom or report selection.
- Range ticks animate `left`; authenticity bars animate `height`; the audio playhead animates `left`. Acceptance: equivalent positions/lengths use transforms, and reduced motion stays static.
- Known voices truncate the primary identifying name and take its first Unicode code point as an avatar. Acceptance: names remain readable, the avatar uses a complete grapheme, and realistic content cannot push actions outside its container.
- Deletion state is excluded from the shared enrollment action lock. Acceptance: a pending removal cannot overlap conflicting mutations; failure retains the voice and retry path.
- Reports must retain neutral unknown identity, no green authority verification, insufficient no-score, sample labels and supplied references.

## Completion record

Pending execution. Real backend inference and physical iOS/Android hardware are unavailable; browser fixtures and emulation cannot certify those integrations.
