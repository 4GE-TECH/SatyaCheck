---
name: SatyaCheck
description: The listening room. Voice screening explained through identity, authenticity and intent, drawn from the recording itself.
colors:
  night-ground: "#050611"
  night-raise: "#0a0c21"
  panel: "#0d102b"
  panel-2: "#13173a"
  panel-3: "#1a1f4a"
  glass: "rgb(10 12 34 / 0.84)"
  line: "rgb(146 156 255 / 0.13)"
  line-2: "rgb(146 156 255 / 0.24)"
  text: "#eef0ff"
  text-2: "#bcc1e8"
  muted: "#8d93c2"
  accent: "#5f6bff"
  accent-hover: "#7681ff"
  accent-ink: "#ffffff"
  accent-soft: "rgb(95 107 255 / 0.16)"
  focus: "#9aa2ff"
  voice-1: "#3c56ff"
  voice-2: "#7a5cff"
  voice-3: "#39c6ff"
  safe: "#43e0a4"
  safe-soft: "rgb(67 224 164 / 0.12)"
  safe-line: "rgb(67 224 164 / 0.34)"
  caution: "#ffc24f"
  caution-soft: "rgb(255 194 79 / 0.12)"
  caution-line: "rgb(255 194 79 / 0.36)"
  danger: "#ff5f6f"
  danger-soft: "rgb(255 95 111 / 0.13)"
  danger-line: "rgb(255 95 111 / 0.38)"
  neutral: "#a3aad6"
  neutral-soft: "rgb(163 170 214 / 0.12)"
  neutral-line: "rgb(163 170 214 / 0.3)"
typography:
  display:
    fontFamily: "Geist Variable, Noto Sans Devanagari Variable, system-ui, sans-serif"
    fontSize: "clamp(2.8rem, 1.5rem + 3.9vw, 5.1rem)"
    fontWeight: 650
    lineHeight: 1
    letterSpacing: "-0.04em"
  headline:
    fontFamily: "Geist Variable, Noto Sans Devanagari Variable, system-ui, sans-serif"
    fontSize: "clamp(2.4rem, 1.4rem + 3vw, 4rem)"
    fontWeight: 640
    lineHeight: 1.02
    letterSpacing: "-0.04em"
  title:
    fontFamily: "Geist Variable, Noto Sans Devanagari Variable, system-ui, sans-serif"
    fontSize: "clamp(1.5rem, 1.2rem + 0.9vw, 2rem)"
    fontWeight: 640
    lineHeight: 1.15
    letterSpacing: "-0.035em"
  body-lg:
    fontFamily: "Geist Variable, Noto Sans Devanagari Variable, system-ui, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 400
    lineHeight: 1.55
  body:
    fontFamily: "Geist Variable, Noto Sans Devanagari Variable, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "Geist Variable, Noto Sans Devanagari Variable, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: 1.35
  numeral:
    fontFamily: "Geist Mono Variable, ui-monospace, Cascadia Mono, Consolas, monospace"
    fontSize: "clamp(5.5rem, 3.5rem + 5vw, 8.5rem)"
    fontWeight: 400
    lineHeight: 0.85
    letterSpacing: "-0.04em"
    fontFeature: "tnum"
rounded:
  sm: "8px"
  md: "12px"
  lg: "18px"
  xl: "24px"
  card: "30px"
  bezel-tray: "34px"
  bezel-plate: "27px"
  pill: "999px"
spacing:
  gutter: "32px"
  gutter-tablet: "20px"
  gutter-small: "14px"
  page: "1280px"
  panel-x: "26px"
  block: "44px"
  chapter: "120px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    rounded: "{rounded.pill}"
    padding: "0 20px"
    height: "44px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  button-primary-large:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    rounded: "{rounded.pill}"
    padding: "0 7px 0 26px"
    height: "54px"
  button-secondary:
    backgroundColor: "{colors.panel-2}"
    textColor: "{colors.text}"
    rounded: "{rounded.pill}"
    padding: "0 20px"
    height: "44px"
  button-secondary-hover:
    backgroundColor: "{colors.panel-3}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.text-2}"
    rounded: "{rounded.pill}"
    padding: "0 20px"
    height: "44px"
  button-ghost-hover:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.text}"
  button-danger:
    backgroundColor: "{colors.danger-soft}"
    textColor: "{colors.danger}"
    rounded: "{rounded.pill}"
    padding: "0 20px"
    height: "44px"
  input:
    backgroundColor: "{colors.panel-2}"
    textColor: "{colors.text}"
    rounded: "{rounded.md}"
    padding: "0 16px"
    height: "48px"
  tone-chip-safe:
    backgroundColor: "{colors.safe-soft}"
    textColor: "{colors.safe}"
    rounded: "{rounded.pill}"
    padding: "0 12px"
    height: "28px"
  tone-chip-neutral:
    backgroundColor: "{colors.neutral-soft}"
    textColor: "{colors.neutral}"
    rounded: "{rounded.pill}"
    padding: "0 12px"
    height: "28px"
  flag-concern:
    backgroundColor: "{colors.danger}"
    textColor: "#ffffff"
    rounded: "{rounded.pill}"
    padding: "0 10px"
    height: "28px"
  nav-link:
    textColor: "{colors.muted}"
    rounded: "{rounded.pill}"
    padding: "0 16px"
    height: "40px"
  nav-link-active:
    textColor: "{colors.text}"
  panel:
    backgroundColor: "{colors.panel}"
    rounded: "{rounded.xl}"
    padding: "20px 26px"
---

# Design System: SatyaCheck

## Overview

**Creative North Star: "The Listening Room"**

A near-black room lit only by the voice under examination. The ground is a deep blue-black (night-ground), behind which an original WebGL field of five luminous voice ribbons drifts, leans toward the pointer and swells with the live microphone level. A fixed film grain sits over everything. Every evidential image comes from the recording itself: a real spectrogram, time-aligned evidence lanes, fusion wires whose stroke weight follows the actual fusion weights. The system declines the category defaults of a score dial, a hero metric and rows of equal cards.

The form is "Ethereal Glass": a floating, frosted island nav, pill-shaped controls whose trailing icon sits in its own circle, and soft inset-hairline panels. Exactly two surfaces are raised into a double bezel, a plate seated in a tray: the home composer and the report verdict. Everything else is flat, separated by hairlines. Density is generous and type is large, because a judge reads this from three metres away on a projector and a protected person reads it under stress.

The effects are author-original, written in the animation-template categories (ambient field, top dock, inline wordmark wave, stacking cards, SplitText reveals). The template sources were unavailable, so nothing here is, or claims to be, a ThreeUI or Neuform component. Dark is the room; light is the same room in daylight, and both follow the system preference.

The Android companion mirrors this world: the night/day `Palette` ThemeExtension, Geist, pill buttons, the bezel and worded flags in `satyacheck_mobile/lib/theme.dart`. That file is the Flutter mirror. This document is the source.

Motion is part of the world. GSAP 3 with ScrollTrigger and SplitText. The house curves are expo.out, power3.out (the default, 0.6s) and power2.inOut, with the CSS ease cubic-bezier(0.32, 0.72, 0, 1). Things settle and never bounce. The one exception is the dock's proximity spring (elastic.out(1, 0.55)), which is used on nav links only.

**The Visible By Default Rule.** Content is in the DOM and visible before any script runs. Scroll entrances animate position only (blocks rise 36px) and never fade from zero, so captures, print and assistive technology see everything at once.

**The Settled Start Rule.** Under prefers-reduced-motion, every timeline is skipped and every element renders at rest. The ribbon field draws one still frame, CSS animations collapse to 1ms, and the nav-pill view transition is disabled.

**Key Characteristics:**
- Near-OLED blue-black ground with a live WebGL voice-ribbon field and fixed grain
- Voice colours belong to audio and tone colours belong to verdicts, with no crossover
- Geist for words, Geist Mono for every figure, tabular
- Pills everywhere you press; 24–34px soft corners everywhere you read
- Double bezel on two surfaces only; everything else flat with inset hairlines
- Motion settles and never hides content; reduced motion starts everything at rest

## Colors

A cold indigo night with one electric accent, three voice blues lifted from the logo, and four verdict tones that each come with a soft fill and a hairline.

### Primary
- **Signal Indigo** (accent): primary buttons, focus treatment, the selected palette row, input focus ring (as accent-soft), numbered-step badges. Hover lifts to accent-hover. Light theme deepens it to #3a43f2.

### Secondary
- **Logo Voice Blues** (voice-1 cobalt, voice-2 violet, voice-3 cyan): reserved for audio. The ambient ribbons, the inline headline wave, the voice-print traces, the enrollment target fill, the route sweep, the playhead glow, the avatar gradient, icons that mean "listening". Never used to signal a verdict.

### Tertiary
- **Verdict Tones** (safe mint, caution amber, danger coral, neutral lavender-grey), each with a `-soft` fill and a `-line` hairline. They colour tone chips, flags, notices, the verdict wash, the plan block, the trust number, fusion wires and scale zones. The report sets `--tone`, `--tone-soft` and `--tone-line` once at its root, and every child reads them.

### Neutral
- **Night Ground** (night-ground): page background, behind the field.
- **Night Raise** (night-raise): recessed wells: the composer stage, spectrogram lanes, slice visuals, mic stage.
- **Panel / Panel 2 / Panel 3** (panel, panel-2, panel-3): card surface; inputs and secondary buttons; pressed segments, skeleton highlights, the scale track.
- **Glass** (glass): floating chrome only. The island nav and mobile tab bar sit behind `saturate(1.8) blur(22px)`; the composer's file chip uses a lighter `blur(14px)`.
- **Hairlines** (line, line-2): every divider and inset border, tinted indigo, never grey.
- **Ink** (text, text-2, muted): headings and values; body and ledes; captions, hints and axis labels.

### Named Rules
**The Two Families Rule.** Voice colours draw audio, and tone colours state a judgement. A cyan bar never means "fine", and a green never decorates a waveform.

**The Earned Green Rule.** Safe green appears only when verification is reachable: an identity check whose voiceprint match is not flagged synthetic or replayed. An authority check (unknown speaker) tops out at neutral "Unverified". A match on a synthetic or replayed voice reads "Sounds like [name]", flagged "Not trusted", in neutral, because a clone that matches is the attack and offers no reassurance.

**The No Score Rule.** Insufficient audio shows no number. The score slot holds a neutral em dash and a sentence saying why.

## Typography

**Display Font:** Geist Variable (with Noto Sans Devanagari Variable, system-ui)
**Body Font:** Geist Variable (same stack, so Hindi and Hinglish set in the same line)
**Label/Mono Font:** Geist Mono Variable (with ui-monospace, Cascadia Mono, Consolas)

**Character:** A neutral, tightly tracked grotesk that stays calm at 5rem. Mono is the voice of measurement: every score, time, weight and frequency, set in tabular figures.

### Hierarchy
- **Display** (650, clamp(2.8rem → 5.1rem), 1.0, -0.04em): the home hero headline only, max 12ch, with the inline wave pill set into the line.
- **Headline** (640, clamp(2.4rem → 4rem), 1.02, -0.04em): the verdict headline, page heads, chapter heads and the closing call (each clamps within the 2–4.6rem band).
- **Title** (640, clamp(1.5rem → 2rem), 1.15, -0.035em): report block heads, slice heads, stack-card titles.
- **Body large** (400, 1.125–1.1875rem, 1.55–1.6): ledes, verdict summary, plan steps, script text. Ledes cap at 44–62ch.
- **Body** (400, 1rem, 1.55): running copy, capped near 66–72ch.
- **Label** (600, 0.875rem): field labels, lane labels, table heads, meta terms. Sentence case, never uppercase, never below 0.75rem, and secondary text never below 14px.
- **Numeral** (Geist Mono 400, up to clamp(5.5rem → 8.5rem), 0.85): the trust count. Smaller mono figures (fusion risk 2rem, result 3.75rem, clocks 1.5–3.5rem) share the weight.

### Named Rules
**The Mono Means Measured Rule.** If it was computed from the audio, it is set in Geist Mono with tabular figures. If it was written by a person, it is set in Geist.

**The Sentence Case Rule.** Headings, labels, chips and flags are sentence case. Shouting reply templates are calmed before display; acronyms such as UPI and OTP keep their capitals.

## Layout

A centred page of 1280px plus a 32px gutter (20px under 900px, 14px under 380px). The main area pads 56px at the top and 96px at the bottom. Under 900px the bottom pad clears the floating tab bar (120px plus the safe area).

The home is an editorial split: copy left (1fr) and the bezelled composer right (1.08fr) at a 64px gap, filling up to min(760px, viewport − 140px). Chapters follow at 120px spacing (88px on small screens), with the principle statement and finale at 160px. The report is a single column of flat blocks, each a 44px band divided by a top hairline, with two-up pairs (1.25fr / 1fr) for transcript and measurements.

Breakpoints are 1100px (split layouts collapse to one column, fusion wires hide), 900px (the island loses its links and a five-tab glass bar docks at the bottom; the accordion stacks; stacking cards stop sticking), 720px (bezel tightens, primary actions go full width, the measurement table restacks into rows) and 380px.

## Elevation & Depth

Depth here is mostly tonal and inset: panels are a lighter indigo than the ground and are outlined with an inset hairline that carries a 1px top highlight, like light catching a glass edge. Real cast shadows are long, soft and negative-spread, so they read as darkness pooling beneath a surface and never as an offset edge. Two surfaces get the full tray-and-plate bezel. Glass blur is reserved for floating chrome.

### Shadow Vocabulary
- **Rest** (`box-shadow: 0 1px 0 rgb(255 255 255 / 0.04) inset, 0 12px 32px -18px rgb(0 0 0 / 0.8)`): default panel.
- **Lifted** (`box-shadow: 0 1px 0 rgb(255 255 255 / 0.05) inset, 0 30px 80px -30px rgb(0 0 0 / 0.9)`): the live room, the command palette, the skip link.
- **Bezel tray** (`box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--text) 9%, transparent), 0 40px 100px -40px rgb(0 0 0 / 0.55)`): the composer and verdict trays.
- **Accent glow** (`box-shadow: 0 1px 0 rgb(255 255 255 / 0.22) inset, 0 8px 24px -10px var(--accent)`): primary buttons and the play control; the record button uses the same shape in danger.

### Named Rules
**The Two Bezels Rule.** Only the composer and the verdict sit in a double bezel (7px tray padding, 34px tray and 27px plate corners). A third bezel dilutes the two moments that matter.

**The Inset Hairline Rule.** Cards draw their edge with `inset 0 0 0 1px` in a line token, not with a CSS border, so tone fills and gradients run to the corner.

## Shapes

Everything you press is a full pill (999px): buttons, chips, flags, segmented controls, nav links, the island itself. Everything you read is a soft, large-radius slab: 24px panels, 28–32px slices, stack cards and the live room, 30px report panels, 22px wells and marquee cards, 16–18px inner wells and list rows. Small fixed squares (avatars and icon tiles, 16–18px corners) are the only squircles. Icons are Phosphor line or fill glyphs at 16–24px.

## Components

### Buttons
Tactile glass pills that compress on press.
- **Shape:** full pill (999px), three heights (34 / 44 / 54px).
- **Primary:** accent with white ink, top inner highlight and an accent glow beneath.
- **Hover / Focus:** primary lifts to accent-hover and the glow lengthens; active scales to 0.97; focus shows a 2px focus-colour outline at a 3px offset.
- **Trailing icon:** when a button carries a trail, the icon sits in its own 32px circle (40px on large) at 16% white, and nudges up and right (translate(2px, -1px) scale(1.06)) on hover.
- **Secondary / Ghost / Danger:** panel-2 with a line-2 hairline; transparent with text-2 that fills to accent-soft; danger-soft fill with danger ink and danger-line. Disabled primary goes to panel-3 with muted ink and stays legible.

### Chips and flags
- **Tone chip:** a pill outlined in the tone's line, filled with its soft fill, tone-coloured text and a leading 8px dot with a 3px halo. Two sizes (28 / 36px).
- **Flag:** a worded pill ("Concern", "Below minimum", "Expected", "Not assessed", "Not trusted"). Concern is solid danger with white text; the others are tinted or outlined. A flag is always a word and never a letter or a colour alone.

### Cards / Containers
- **Corner Style:** 24px panel, 28–32px for signature slabs.
- **Background:** panel; tone-tinted variants blend 12–14% of a tone or voice-1 into panel through a 120–170° linear gradient.
- **Shadow Strategy:** Rest; see Elevation.
- **Border:** inset hairline (line or line-2).
- **Internal Padding:** 20px × 26px heads and bodies, 32–48px on hero slabs.

### Inputs / Fields
- **Style:** 48px tall, 12px corners, panel-2 fill, line-2 hairline.
- **Focus:** border turns accent, a 4px accent-soft ring, fill lifts to panel.
- **Segmented control:** a pill track on panel-2 with a raised panel-3 thumb for the pressed option.

### Navigation
A floating glass island, 60px tall and centred under a 16px top offset. It holds the logo mark (30px, 9px corners, voice-1 glow) and wordmark, five links, then the tools (search with a key hint, health dot, theme) behind a hairline divider. Links are muted at weight 520 and turn to text when hovered or active. The active pill is a 9% text tint with an inset hairline. Route changes run as view transitions, so only the named nav pill glides between links (0.5s, cubic-bezier(0.16, 1, 0.3, 1)) while the page itself rises 18px under a 2px voice-gradient sweep. On fine pointers, links spring toward the cursor like a dock. Under 900px the links move to a bottom glass tab bar with 26px corners.

### Verdict
The report's raised moment: a tone chip, a masked word-by-word headline, a summary and a four-term meta row on the left, with the trust count on a reference scale on the right. The scale has four interval zones (0–35 / 35–60 high risk and suspicious, 60–85 caution, 85–100 verified or unverified) and a 6px marker. A tone-tinted radial wash blooms behind the content.

### Evidence lanes
A recessed well (night-raise, 22px corners) of time-aligned lanes: spectrogram, per-segment synthetic bars against a dashed danger threshold, speech blocks tinted concern or reassure, an identity band, and a time axis. A white playhead with a voice-3 glow scrubs all lanes together.

### Inline wave
A pill set into the hero headline, 1.9em by 0.72em, filled with voice-1 and rimmed in voice-3, holding bars that pulse with the voice field.

## Do's and Don'ts

### Do:
- **Do** keep voice-1, voice-2 and voice-3 on audio imagery and the four tones on judgements (The Two Families Rule).
- **Do** gate green on a verifiable identity check: a voiceprint match not flagged synthetic or replayed. Otherwise use neutral.
- **Do** render a voiceprint match on a synthetic or replayed voice as "Sounds like [name]" with a neutral "Not trusted" flag.
- **Do** show insufficient audio as an em dash and an explanation, never a number.
- **Do** write every flag as a word in a pill ("Concern", "Expected", "Not assessed").
- **Do** set every computed figure in Geist Mono with tabular numerals.
- **Do** reserve the double bezel (7px tray, 34px / 27px corners) for the composer and the verdict.
- **Do** make every pressable element a full pill, and put a trailing icon in its own circle.
- **Do** draw evidence from the recording itself (spectrogram, segment bars, transcript marks), and weight fusion wires by the real weights.
- **Do** keep content visible without JavaScript, and start everything settled under reduced motion.

### Don't:
- **Don't** show green for an unknown speaker or an authority check. The top band reads "Unverified" in neutral.
- **Don't** use a score dial, a single hero metric or rows of equal cards to present a verdict.
- **Don't** fade content in from zero opacity on scroll or on route change.
- **Don't** add a third bezel or put glass blur on content cards. Blur belongs to floating chrome.
- **Don't** use uppercase labels or letter flags (H, L, OK) on screen.
- **Don't** cast hard or offset shadows. Shadows are long, soft and negative-spread.
- **Don't** describe any effect as ThreeUI, Neuform or another template library's. They are original work in those categories.
