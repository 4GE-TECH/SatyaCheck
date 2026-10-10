# Acceptance: when the WebRTC hand-off is done

Tick each item and note the date and the phones used. The backend side is already checked by
`python -m scripts.webrtc_smoke`. This list checks the parts only real phones can.

## Build

- [ ] On a laptop that never had this project: clone, follow [EXPO.md](EXPO.md) exactly, and
      get a development APK. Note any step that had to be changed, and fix the doc.
- [ ] The APK installs on two Android phones and opens to the sign-in screen.

## Same Wi-Fi

- [ ] Two different accounts sign in, one per phone, with emailed codes.
- [ ] Phone A starts a call and shows a code; phone B joins with it.
- [ ] Each person hears the other, both ways, with no echo or one-way audio.
- [ ] Within about 10 s of speech, each phone shows a band about the **other** person.
      Unverified (grey) is correct for a stranger.
- [ ] A enrolls B's voice through the web app, as A's account. On the next call, A sees B as
      verified (green), and B does not see anything about A's enrollments.
- [ ] Playing a scam script (`data/eval_set/clips/held-family-emergency-001.wav`, through a
      speaker into B's mic) moves A's banner to caution or worse, and the alert stays after
      the script stops.

## Rules from BACKEND_API.md

- [ ] The screening agent never appears as a person in the call UI.
- [ ] Phone B turns airplane mode on for 10 s, then off. B's call resumes, and the banner
      comes back with the same or a worse band, never reset to green.
- [ ] Stop the backend mid-call. Both phones show "Screening unavailable" and the call itself
      continues.
- [ ] `insufficient` shows "Listening…" with no number.

## Mobile data (the real test)

- [ ] Both phones on **mobile data**, with Wi-Fi off. Do the call, the scam-script check, and
      the airplane-mode check again. Note which [NETWORK.md](NETWORK.md) option was used.
- [ ] Note the time from the first spoken word to the first non-grey band, and how audio
      quality felt.

## Report

Attach to the pull request:

- the phone models and Android versions;
- the network option;
- the timings;
- a screen recording of one call with the banner changing;
- anything that surprised you.
