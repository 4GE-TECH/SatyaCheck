# SatyaCheck / Signal observatory

An independent frontend built from scratch in `web2`. The existing `web` application is not required to run it.

## Run

```powershell
cd web2
npm ci
npm run dev
```

Open http://127.0.0.1:5174. Vite proxies `/api` to the existing server at http://127.0.0.1:8000. Keep that service running for screening, enrollment, removal and saved-report retrieval. Clearly labelled illustrative samples work without it; service errors never become sample verdicts.

## What is implemented

- Listening desk: upload, drag/drop, preview, nearby microphone capture, cancellation and real screening API submission.
- Known voices: list, consent-based enrollment, replacement recording and confirmed removal.
- Evidence: all six result bands, fixed trust score, three signals, authenticity timeline, transcript, concerning/reassuring markers, cited reasons and recommended actions.
- Reports: in-memory session library, server lookup by ID, copy summary, JSON export and browser print/PDF.
- Responsive guide, keyboard navigation, focus-managed dialogs and reduced-motion support.

All artwork and fonts are local. No browser storage APIs, remote font services or external runtime assets. Session reports disappear on refresh; server reports can be retrieved by ID. The interface does not continuously stream calls. Nearby capture must use a separate device during cellular calls. Silence is rejected using measured amplitude, not buffer length.

## Checks

```powershell
npm run build
npm run lint
npm test
```

Playwright uses installed Google Chrome on Windows (see `playwright.config.ts` for an executable override). Tests cover mocked API success/failure, neutral authority results, quality refusal, malformed evidence, cancellation, enrollment confirmation, removal, microphone denial/silence, keyboard focus, exports and responsive layouts from 320 to 1440 pixels. Screenshots are saved in `design/review`. These checks do not validate live model inference or physical microphone hardware.

## Structure

`src/pages` holds independently authored screens; `src/components` contains the visual and audio controls; `src/lib` contains API validation, capture lifecycle and illustrative samples. `contracts.ts` preserves the backend's existing field shapes. React 18, TypeScript, Vite, Motion and Lucide; no component library.
