# Frontend overhaul

SatyaCheck now uses the Clarity workspace: a graphite sidebar, silver surfaces, coral actions, a fine acoustic ribbon, and a mobile bottom navigation dock. Check audio, known voices, reports and help share the new system. The existing API workflows and evidence semantics are preserved.

The implementation is in `src/components/Layout.tsx`, `VoiceHero.tsx`, `VoiceHero.css`, `AudioInput.tsx`, `src/pages/ScreenPage.tsx`, and `src/index.css`. `DESIGN.md` records the implemented layout, tokens, interactions and product rules. This direction supersedes the earlier polish plan's indigo/WebGL appearance.

## Run

From `web/`:

```sh
npm run dev -- --host 127.0.0.1 --port 5173
npm run build
npm run lint
npm test
npm run test:ui
```

The test browser defaults to installed Windows Chrome. Set `SATYACHECK_TEST_BROWSER` to another Chromium executable if needed. Vite proxies local API requests to port 8000. Deployment needs SPA fallback and a same-origin `/api` proxy including WebSocket upgrades. Microphone capture requires HTTPS or localhost.

## Review findings and decisions

Review was documentation-led: `AGENTS.md`, `PRD.md`, `PLAN.md`, frontend product/design docs, and only frontend entry points and shared task components. No model or backend implementation audit was performed.

The previous presentation placed a substantial animated introduction ahead of the task. The new hierarchy emphasizes input and clear next steps, with signal explanations alongside. Stable desktop navigation becomes a reachable bottom dock on phones. The visual language extends to enrollment, reports, empty states, help and errors.

The existing frontend had valuable safeguards: service failures never become fabricated results, enrollment requires a returned voiceprint, unknown identities remain neutral, failed quality suppresses scores, and live reports require the matching final acknowledgement. Those behaviors remain in place.

Motion is finite and purpose-driven: a one-time ribbon entrance, short route entry, interruptible tab translation and press feedback. Numerical evidence is immediately readable. Reduced motion stays static. No new dependency, remote asset request, browser storage, backend field or product capability was added.

## Verification and limits

- Production build and lint pass.
- 10 unit tests and 22 browser tests pass.
- Browser tests cover all result bands, failures, enrollment, report retrieval, multilingual long data, enlarged text, keyboard use, reduced motion, mobile navigation, live finalization and interruption, and print colors.
- Desktop/mobile light and dark screenshots were visually inspected. Captures are under `.impeccable/review/`.
- APIs were intercepted with fixtures; live inference was not validated. Physical-device microphone, keyboard, touch and safe-area behavior still need hardware validation.

All edits for this task are inside `web/`. Work remains uncommitted on `frontend-overhaul`; no push was performed.
