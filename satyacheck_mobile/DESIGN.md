---
name: "SatyaCheck Android"
description: "Native Material 3 voice screening with readable evidence."
colors:
  primary: "#3028ED"
  page: "#FDFAE7"
  surface: "#FFFFFF"
  ink: "#0C0D1E"
  dark-primary: "#B5AFFF"
  dark-on-primary: "#21194E"
  dark-page: "#0C0D1E"
  dark-surface: "#17182C"
  dark-ink: "#F5F3EB"
  verified: "#266047"
  caution: "#885917"
  danger: "#9D3836"
  dark-verified: "#A9D8B6"
  dark-caution: "#E7C78D"
  dark-danger: "#F2B4B0"
typography:
  body:
    lineHeight: 1.5
  title:
    fontWeight: 600
rounded:
  badge: "8px"
  control: "12px"
  surface: "18px"
spacing:
  compact: "8px"
  label-gap: "12px"
  message-inset: "16px"
  surface-inset: "22px"
  page-inset: "24px"
  section-gap: "28px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "14px 20px"
  button-outlined:
    rounded: "{rounded.control}"
    padding: "14px 20px"
  button-text:
    textColor: "{colors.primary}"
  input:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.control}"
    padding: "16px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.surface}"
    padding: "22px"
  badge:
    rounded: "{rounded.badge}"
    padding: "7px 12px"
---

# Design System: SatyaCheck Android

## Overview

**Creative North Star: "Family correspondence"**

The shared family-correspondence identity is expressed through native Material 3 surfaces and controls. Warm ivory and ink frame the supplied local logo; electric blue identifies actions and pale violet carries those actions in dark mode.

This record describes lib/theme.dart, lib/main.dart and lib/result_screen.dart. Generated Material scheme values remain owned by Flutter rather than frozen as guessed hex tokens. Source inspection is complete; final device visual signoff remains pending.

**Key Characteristics:**
- Native Material 3 controls and navigation.
- Shared brand palette with separate evidence colors.
- Safe areas, scrolling content and theme-based text sizing.

## Colors

### Primary
Electric blue (`primary`) fills main actions. Dark mode changes primary to pale violet and uses the dedicated dark-on-primary ink. Other Material role colors derive from the same seed through ColorScheme.fromSeed; those generated values are not duplicated here.

### Neutral
Ivory (`page`) and white (`surface`) support the light scheme. Ink ground, a lighter dark surface and warm light text form the dark scheme. Outline, on-surface-variant, primary-container and error roles remain Flutter scheme values.

### Named Rules
**The Evidence Color Rule.** Reserve verdict colors for labeled evidence states; brand blue is an action color. Unverified and insufficient remain neutral, and insufficient has no score.

Verified uses green, caution amber, and suspicious/high-risk red, each with a dedicated dark text color. Unverified and insufficient use onSurfaceVariant. Badge backgrounds and borders derive from the verdict color at .09 and .35 alpha respectively.

## Typography

Material 3 TextTheme supplies the type hierarchy, locale behavior and platform family; no custom or remote font is declared. The implementation modifies bodyLarge/bodyMedium height to 1.5 and titleLarge/titleMedium weight to 600. Page/result headings request headlineMedium with weight 600 and letter spacing -0.6; headlineLarge has spacing -1. Those system-family headline overrides are observed drift, not a new branded display specification. Concrete framework font metrics remain framework-owned instead of guessed source tokens.

## Layout

SafeArea surrounds the main content. Scrollable pages normally use 24 logical-pixel insets; the home page uses 24/16/24/28 edges. Content is centered and capped at 700 logical pixels. At a window width of 700 or more, the bottom navigation becomes a labeled NavigationRail. Surface content uses 22-pixel padding, messages 16, and sections commonly separate by 28. Native text scaling and wrapping remain active.

## Elevation & Depth

Cards and app bars have zero elevation; app bars also disable scrolled-under elevation. Tonal surface distinctions and outlineVariant borders provide depth. Native Material state layers handle pressed, hover and focus feedback; the app does not define a custom animation or shadow system.

## Shapes

Surfaces use broad rounded corners and fine scheme outlines. Buttons and fields share the control radius; verdict labels use a tighter badge radius. The supplied logo is clipped into a softly rounded 34-pixel square in the app bar.

## Components

### Buttons
Filled and outlined actions share a 48 by 52 minimum size and symmetric 20 horizontal/14 vertical padding. Text actions have a 48 by 48 minimum. Their colors and enabled, pressed, hover, focus and disabled behavior are supplied by Material 3 and the active scheme.

### Inputs / Fields
Outlined, filled fields use surface fill, the control radius and 16-pixel content padding. Native focus and error feedback remain Material-owned.

### Cards / Containers
Surface wraps a zero-margin, zero-elevation Card with outlineVariant border and 22-pixel padding. InfoMessage uses surfaceContainerHighest or errorContainer, an icon and a live-region semantic announcement; an optional recovery action follows the text.

### Chips
VerdictBadge is a noninteractive evidence label. It uses labelLarge, semantic text color and derived translucent fill and border, with a written label in every band.

### Navigation
Check, Voices, Recent and Setup use native navigation destinations with labels always visible. Wide layouts use the equivalent labeled rail. System Back returns from a secondary destination to Check before leaving the root.

### Evidence summary
A surface groups the verdict badge, conclusion, matched name when verified and a score with its limits. Insufficient audio shows a no-score sentence. Evidence sections follow as scrollable content, with title and body roles retained.

## Do's and Don'ts

### Do:
- Do retain the original locally bundled logo.
- Do pair verdict color with a plain-language label.
- Do preserve neutral unknown identity and unscored insufficient audio.

### Don't:
- Don't use brand blue as a trust verdict.
- Don't add remote fonts or fabricated evidence.
