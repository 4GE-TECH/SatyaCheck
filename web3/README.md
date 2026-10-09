# SatyaCheck web (web3)

A from-scratch dashboard for SatyaCheck. You check a recording, read an evidence report, listen to a live call from a second device, and manage known voices.

## Run

```sh
cd web3
npm ci
npm run dev            # http://127.0.0.1:5175, proxies /api (HTTP and WebSocket) to localhost:8000
npm run build          # type-check and production build into dist/
npm run lint
npm test               # unit tests: band rules, fusion signals, WAV encoding, parsing
npm run test:ui        # Playwright, using installed Chrome with a fake microphone
```

The browser tests intercept every service call and the WebSocket, so they never touch a real service or enroll real voices. Set `SATYACHECK_TEST_BROWSER` to use a Chromium other than the Windows default Chrome. The 10-second test tone in `tests/fixtures/` is synthetic and only used by tests.

## Deploy

Serve `dist/` with an SPA fallback to `index.html`. Proxy `/api/*`, including WebSocket upgrades for `/api/ws/*`, to the screening service on the same origin. Fonts and the logo are bundled, so the app makes no external requests. Microphone features need HTTPS or localhost.

## What it does

- **Check**: upload a file or record a clip. The file is decoded in the browser and its real waveform is drawn, then it is sent to `POST /api/screen`.
- **Report**: the verdict and a trust score set on its reference interval, a "Do this now" action plan, a fusion diagram built from the response's `weights_used` and branch risks, and a time-aligned evidence scrubber. The scrubber shows the real spectrogram (computed in a Web Worker) plus lanes for synthetic score, speech and identity, all on one playhead. Below that: the transcript with marked phrases, quality checks, and evidence with sources. Copy, print and the service PDF are available.
- **Listen live**: streams 3-second 16 kHz WAV slices to `/api/ws/screen/{id}`. It shows a scrolling live spectrogram, a provisional read that updates in place, and trust over time. Stopping sends the final slice and opens the full report, including the captured audio. Silent input is detected by amplitude, not sample count, and a warning is shown.
- **Known voices**: enroll with a bilingual script, live level and a progress bar toward 30 seconds of speech, with explicit consent. You can re-record a person, or remove them after an inline confirmation (`DELETE /api/persons/{id}`). Success is shown only when the service returns a voiceprint.
- **Reports**: reports from this session, plus lookup of a saved report by session ID.
- **Ctrl/⌘ K**: a command menu for pages, recent reports and labelled samples.

## Rules it keeps

- An unknown speaker is shown as *unverified* (neutral), never as verified. Authority-check mode never shows green.
- Insufficient audio gets no score.
- A synthetic voice is explained as gated by intent.
- The app gives a score with evidence, never a binary fraud verdict.
- Samples are labelled everywhere they appear.
- No browser storage: reports for this session live in memory only.
- Reduced motion is honoured, and every entrance starts settled.
