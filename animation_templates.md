---
name: add-portal-field
description: "Build Portal Field from its verified authored source using Three.js r134 + Raw WebGL + Canvas 2D, including the complete renderer, interactions, and required assets. Use when Codex needs to implement, port, or adapt this effect without requiring the ThreeUI package or reconstructing the visual from an approximation."
---

# Build Portal Field

## Description

Five ambient field backgrounds collected across Three.js, raw WebGL, and Canvas 2D renderers.

Recreate the authored behavior from the verified source, not from screenshots or the abbreviated orchestration sample in this skill. The implementation may live directly in the target project and does not require `@designcodeio/threeui`.

## Technologies

- React variant host
- Three.js ShaderMaterial
- Raw WebGL fullscreen renderers
- Canvas 2D particle and ember composites
- Lazy-loaded variant sources

## Verified source material

- `src/shaders/portal-field/PortalFieldCollection.tsx`
- `src/shaders/neuform-isolated/NeuformBatchEffects.tsx`
- `src/shaders/neuform-isolated/sources/portal-field.html`
- `src/shaders/neuform-isolated/sources/flow-field.html`
- `src/shaders/neuform-isolated/NeuformIsolatedEffects.tsx`
- `src/shaders/neuform-isolated/sources/strata-cloud.html`
- `src/shaders/stream-convergence/StreamConvergenceBackground.tsx`
- `src/shaders/stream-convergence/streamConvergenceShaders.ts`
- `src/shaders/bell-field/BellFieldBackground.tsx`
- `src/shaders/bell-field/bellFieldShaders.ts`

Source revision: `SHA-256 f90e34f83d51`

## Implementation steps

1. Open every verified source file listed above and identify the renderer, host lifecycle, styles, and assets before editing.
2. Keep PortalFieldCollection as the public entry point and select portal-field, flow-field, cloud-field, bell-field, or stream-convergence with the variant prop.
3. Retain each authored renderer and composition at its existing implementation boundary.
4. Keep the common palette and motion controls at the collection boundary while allowing renderer-specific props through the typed variant union.
5. Lazy-load and mount only the selected renderer so inactive WebGL contexts, canvases, timers, and animation loops are not allocated.
6. Preserve every renderer's resize, visibility, interaction, animation-frame, and cleanup lifecycle.
7. Give the local component a sized, overflow-controlled parent and verify desktop, mobile, reduced-motion, and context-loss behavior.

Asset handling: This effect has no required external assets.

## Local component example

Import the copied local component rather than a package entrypoint:

```tsx
import { PortalFieldCollection } from "./effects/portal-field/PortalFieldCollection";
import "./effects/portal-field/styles.css";

export function Scene() {
  return <div className="effect-frame"><PortalFieldCollection /></div>;
}
```

## Core renderer pattern

This excerpt documents orchestration only. Copy the exact shader, geometry, pass, and interaction code from the verified source files.

```tsx
<PortalFieldCollection variant="flow-field" speed={1.1} density={1.2} hue={8} />
```

## Behavior contract

- Runtime: Three.js r134 + Raw WebGL + Canvas 2D
- Passes: 1 selected ambient field composition
- Interaction: Variant selection plus customizable motion, geometry, opacity, and palette
- Assets: No owned binary assets
- **source** (fixed): Exact Neuform HTML
- **focus** (host): Effect-only sandbox
- **speed** (number): 1
- **size** (number): 1
- **length** (number): 1
- **density** (number): 1
- **opacity** (number): 1
- **palette** (optional): Final-frame grade
- **assets** (fixed): No owned binary assets
- **variants** (fixed): Portal + Flow + Cloud + Bell + Stream Convergence

## Verification

1. Compare the rendered composition, animation timing, pointer behavior, and state transitions with the source implementation.
2. Exercise resize, high-DPI, mobile/coarse-pointer, reduced-motion, tab visibility, and WebGL context-loss paths where applicable.
3. Confirm every animation frame, observer, listener, geometry, buffer, texture, framebuffer, material, and renderer is released on teardown.
4. Check the browser console and confirm the effect renders at native-or-better backing resolution.

## Guardrails

- Do not substitute a visually similar package, demo, shader, or runtime.
- Do not approximate, reconstruct, or simplify the authored GLSL, render passes, geometry, interaction state, or assets.
- Keep exact source and asset hashes under regression tests when the source project provides them.
- Adapt only the surrounding host boundary needed by the target project; keep renderer behavior intact.


---
name: add-elements
description: "Build Elements from its verified authored source using Raw WebGL2 + Canvas 2D, including the complete renderer, interactions, and required assets. Use when Codex needs to implement, port, or adapt this effect without requiring the ThreeUI package or reconstructing the visual from an approximation."
---

# Build Elements

## Description

Water, lightning, fire, condensation, and a painterly generative tree collected as one elemental family across WebGL2 and Canvas 2D.

Recreate the authored behavior from the verified source, not from screenshots or the abbreviated orchestration sample in this skill. The implementation may live directly in the target project and does not require `@designcodeio/threeui`.

## Technologies

- React variant host
- Three focused raw WebGL2 Elemental Marks panels
- Painterly Canvas 2D Generative Tree
- Existing transparent Canvas 2D Condensation renderer
- Allow-scripts-only source sandbox
- Lazy-loaded variant boundaries

## Verified source material

- `elemental-marks.html — complete water, lightning, and fire source`
- `src/shaders/elements/sources/elemental-marks.html`
- `src/shaders/elements/ElementsBackground.tsx`
- `src/shaders/elements/ElementsCollection.tsx`
- `generative-tree.html — complete authored Canvas 2D renderer`
- `src/shaders/elements/sources/generative-tree.html`
- `src/shaders/elements/GenerativeTree.tsx`
- `src/shaders/condensation/condensationRenderer.ts`
- `src/shaders/condensation/CondensationBackground.tsx`

Source revision: `SHA-256 7a6871fe99fa`

## Implementation steps

1. Open every verified source file listed above and identify the renderer, host lifecycle, styles, and assets before editing.
2. Keep ElementsCollection as the public entry point and select water, lightning, fire, condensation, or generative-tree with the variant prop.
3. Package the complete Elemental Marks HTML byte-for-byte, focus one authored panel, and apply the documented higher-resolution scale and detail refinements only in the React presentation adapter while preserving its mark paths and pointer behavior.
4. Lazy-load Condensation through its existing renderer and Generative Tree through its byte-exact Canvas 2D sandbox so each lifecycle remains independent.
5. Expose the shared speed, size, particles, opacity, and palette controls for WebGL2 marks and Generative Tree while keeping Condensation's speed, drops, and opacity controls.
6. Mount only the selected family component and preserve sandbox, visibility, reduced-motion, resize, pointer, and cleanup lifecycles.
7. Give the local component a sized, overflow-controlled parent and verify desktop, mobile, reduced-motion, and context-loss behavior.

Asset handling: This effect has no required external assets.

## Local component example

Import the copied local component rather than a package entrypoint:

```tsx
import { ElementsCollection } from "./effects/elements/ElementsCollection";
import "./effects/elements/styles.css";

export function Scene() {
  return <div className="effect-frame"><ElementsCollection /></div>;
}
```

## Core renderer pattern

This excerpt documents orchestration only. Copy the exact shader, geometry, pass, and interaction code from the verified source files.

```tsx
<ElementsCollection variant="lightning" speed={1.1} particleAmount={1.2} />
```

## Behavior contract

- Runtime: Raw WebGL2 + Canvas 2D
- Passes: 1 selected composition — up to 3 WebGL2 passes or 1 Canvas 2D pass
- Interaction: Variant selection, pointer-reactive marks and tree wind, speed, scale, particles, palette, and opacity
- Assets: Three embedded vector brand paths; no external binary assets
- **renderer** (host): Sandboxed WebGL2 or Canvas 2D
- **variants** (fixed): Water + Lightning + Fire + Condensation + Generative Tree
- **source** (fixed): Complete authored Elemental Marks + Generative Tree documents
- **assets** (embedded): Three vector mark paths; no external tree assets

## Verification

1. Compare the rendered composition, animation timing, pointer behavior, and state transitions with the source implementation.
2. Exercise resize, high-DPI, mobile/coarse-pointer, reduced-motion, tab visibility, and WebGL context-loss paths where applicable.
3. Confirm every animation frame, observer, listener, geometry, buffer, texture, framebuffer, material, and renderer is released on teardown.
4. Check the browser console and confirm the effect renders at native-or-better backing resolution.

## Guardrails

- Do not substitute a visually similar package, demo, shader, or runtime.
- Do not approximate, reconstruct, or simplify the authored GLSL, render passes, geometry, interaction state, or assets.
- Keep exact source and asset hashes under regression tests when the source project provides them.
- Adapt only the surrounding host boundary needed by the target project; keep renderer behavior intact.


---
name: add-structure-flow
description: "Build Structure Flow from its verified authored source using Three.js r128–r160, including the complete renderer, interactions, and required assets. Use when Codex needs to implement, port, or adapt this effect without requiring the ThreeUI package or reconstructing the visual from an approximation."
---

# Build Structure Flow

## Description

Thirteen authored Three.js field studies collected as one family, spanning particle domes, horizons, orbital systems, matrices, topology, fluid fields, embers, and vortexes.

Recreate the authored behavior from the verified source, not from screenshots or the abbreviated orchestration sample in this skill. The implementation may live directly in the target project and does not require `@designcodeio/threeui`.

## Technologies

- React typed variant host
- Thirteen authored Three.js r128-r160 field renderers
- Point clouds, ShaderMaterials, topology scenes, fluid fields, embers, and post-process bloom
- Lazy-loaded renderer-specific lifecycles and controls

## Verified source material

- `src/shaders/structure-flow/StructureFlowCollection.tsx`
- `Axiom-Structure-Flow (2).html — Three.js background`
- `src/shaders/structure-flow/structureFlowRenderer.ts`
- `src/shaders/structure-flow/StructureFlowBackground.tsx`
- `src/shaders/emerald-horizon/EmeraldHorizonBackground.tsx`
- `src/shaders/orbital-sphere/OrbitalSphereBackground.tsx`
- `src/shaders/dot-matrix/DotMatrixBackground.tsx`
- `src/shaders/neuform-isolated/NeuformIsolatedEffects.tsx`
- `src/shaders/neuform-isolated/NeuformCraftEffects.tsx`
- `src/shaders/neuform-isolated/NeuformBatchEffects.tsx`

Source revision: `SHA-256 40eb5bac81e3`

## Implementation steps

1. Open every verified source file listed above and identify the renderer, host lifecycle, styles, and assets before editing.
2. Use StructureFlowCollection as the family entry point and select the exact authored renderer with the variant prop.
3. Keep Structure Flow, Emerald Horizon, Orbital Sphere, Dot Matrix, Expanse Field, Logic Core, Dimensional Field, Data Field, Topology Field, Nebula, Fluid Field, Ember Storm, and Flux Vortex as independent scenes rather than blending them into one renderer.
4. Preserve the source-exact Three.js revision, geometry, shaders, camera, palette, motion, and pointer behavior for every variant.
5. Expose each renderer's own controls at the variant boundary and lazy-load only the selected implementation.
6. Retain every source renderer's resize, visibility, animation-frame, context, and disposal lifecycle.
7. Give the local component a sized, overflow-controlled parent and verify desktop, mobile, reduced-motion, and context-loss behavior.

Asset handling: This effect has no required external assets.

## Local component example

Import the copied local component rather than a package entrypoint:

```tsx
import { StructureFlowCollection } from "./effects/structure-flow/StructureFlowCollection";
import "./effects/structure-flow/styles.css";

export function Scene() {
  return <div className="effect-frame"><StructureFlowCollection variant="emerald-horizon" /></div>;
}
```

## Core renderer pattern

This excerpt documents orchestration only. Copy the exact shader, geometry, pass, and interaction code from the verified source files.

```tsx
<StructureFlowCollection variant="flux-vortex" speed={1} density={1} />
```

## Behavior contract

- Runtime: Three.js r128–r160
- Passes: 1–2 Three.js scene, point-cloud, or ShaderMaterial passes
- Interaction: Variant-specific pointer, motion, geometry, opacity, mask, and palette controls
- Assets: No external assets
- **renderer** (variant): Three.js r128–r160
- **variants** (fixed): 13 field studies
- **controls** (adaptive): Renderer-specific
- **assets** (fixed): None

## Verification

1. Compare the rendered composition, animation timing, pointer behavior, and state transitions with the source implementation.
2. Exercise resize, high-DPI, mobile/coarse-pointer, reduced-motion, tab visibility, and WebGL context-loss paths where applicable.
3. Confirm every animation frame, observer, listener, geometry, buffer, texture, framebuffer, material, and renderer is released on teardown.
4. Check the browser console and confirm the effect renders at native-or-better backing resolution.

## Guardrails

- Do not substitute a visually similar package, demo, shader, or runtime.
- Do not approximate, reconstruct, or simplify the authored GLSL, render passes, geometry, interaction state, or assets.
- Keep exact source and asset hashes under regression tests when the source project provides them.
- Adapt only the surrounding host boundary needed by the target project; keep renderer behavior intact.


---
name: add-structure-flow
description: "Build Structure Flow from its verified authored source using Three.js r128–r160, including the complete renderer, interactions, and required assets. Use when Codex needs to implement, port, or adapt this effect without requiring the ThreeUI package or reconstructing the visual from an approximation."
---

# Build Structure Flow

## Description

Thirteen authored Three.js field studies collected as one family, spanning particle domes, horizons, orbital systems, matrices, topology, fluid fields, embers, and vortexes.

Recreate the authored behavior from the verified source, not from screenshots or the abbreviated orchestration sample in this skill. The implementation may live directly in the target project and does not require `@designcodeio/threeui`.

## Technologies

- React typed variant host
- Thirteen authored Three.js r128-r160 field renderers
- Point clouds, ShaderMaterials, topology scenes, fluid fields, embers, and post-process bloom
- Lazy-loaded renderer-specific lifecycles and controls

## Verified source material

- `src/shaders/structure-flow/StructureFlowCollection.tsx`
- `Axiom-Structure-Flow (2).html — Three.js background`
- `src/shaders/structure-flow/structureFlowRenderer.ts`
- `src/shaders/structure-flow/StructureFlowBackground.tsx`
- `src/shaders/emerald-horizon/EmeraldHorizonBackground.tsx`
- `src/shaders/orbital-sphere/OrbitalSphereBackground.tsx`
- `src/shaders/dot-matrix/DotMatrixBackground.tsx`
- `src/shaders/neuform-isolated/NeuformIsolatedEffects.tsx`
- `src/shaders/neuform-isolated/NeuformCraftEffects.tsx`
- `src/shaders/neuform-isolated/NeuformBatchEffects.tsx`

Source revision: `SHA-256 40eb5bac81e3`

## Implementation steps

1. Open every verified source file listed above and identify the renderer, host lifecycle, styles, and assets before editing.
2. Use StructureFlowCollection as the family entry point and select the exact authored renderer with the variant prop.
3. Keep Structure Flow, Emerald Horizon, Orbital Sphere, Dot Matrix, Expanse Field, Logic Core, Dimensional Field, Data Field, Topology Field, Nebula, Fluid Field, Ember Storm, and Flux Vortex as independent scenes rather than blending them into one renderer.
4. Preserve the source-exact Three.js revision, geometry, shaders, camera, palette, motion, and pointer behavior for every variant.
5. Expose each renderer's own controls at the variant boundary and lazy-load only the selected implementation.
6. Retain every source renderer's resize, visibility, animation-frame, context, and disposal lifecycle.
7. Give the local component a sized, overflow-controlled parent and verify desktop, mobile, reduced-motion, and context-loss behavior.

Asset handling: This effect has no required external assets.

## Local component example

Import the copied local component rather than a package entrypoint:

```tsx
import { StructureFlowCollection } from "./effects/structure-flow/StructureFlowCollection";
import "./effects/structure-flow/styles.css";

export function Scene() {
  return <div className="effect-frame"><StructureFlowCollection variant="emerald-horizon" /></div>;
}
```

## Core renderer pattern

This excerpt documents orchestration only. Copy the exact shader, geometry, pass, and interaction code from the verified source files.

```tsx
<StructureFlowCollection variant="flux-vortex" speed={1} density={1} />
```

## Behavior contract

- Runtime: Three.js r128–r160
- Passes: 1–2 Three.js scene, point-cloud, or ShaderMaterial passes
- Interaction: Variant-specific pointer, motion, geometry, opacity, mask, and palette controls
- Assets: No external assets
- **renderer** (variant): Three.js r128–r160
- **variants** (fixed): 13 field studies
- **controls** (adaptive): Renderer-specific
- **assets** (fixed): None

## Verification

1. Compare the rendered composition, animation timing, pointer behavior, and state transitions with the source implementation.
2. Exercise resize, high-DPI, mobile/coarse-pointer, reduced-motion, tab visibility, and WebGL context-loss paths where applicable.
3. Confirm every animation frame, observer, listener, geometry, buffer, texture, framebuffer, material, and renderer is released on teardown.
4. Check the browser console and confirm the effect renders at native-or-better backing resolution.

## Guardrails

- Do not substitute a visually similar package, demo, shader, or runtime.
- Do not approximate, reconstruct, or simplify the authored GLSL, render passes, geometry, interaction state, or assets.
- Keep exact source and asset hashes under regression tests when the source project provides them.
- Adapt only the surrounding host boundary needed by the target project; keep renderer behavior intact.


---
name: add-predictive-arc
description: "Build Predictive Arc from its verified authored source using Canvas 2D + Raw WebGL + Three.js r128, including the complete renderer, interactions, and required assets. Use when Codex needs to implement, port, or adapt this effect without requiring the ThreeUI package or reconstructing the visual from an approximation."
---

# Build Predictive Arc

## Description

Eight animated arc, signal, ribbon, void, and halftone scenes collected in one Canvas 2D, raw-WebGL, and Three.js family.

Recreate the authored behavior from the verified source, not from screenshots or the abbreviated orchestration sample in this skill. The implementation may live directly in the target project and does not require `@designcodeio/threeui`.

## Technologies

- React variant host
- Four Canvas 2D renderers
- Three raw-WebGL renderers
- One Three.js point-field renderer
- Dark/light mode surfaces
- Lazy-loaded variant sources
- ResizeObserver, IntersectionObserver, adaptive pixel ratio, and requestAnimationFrame

## Verified source material

- `Axiom---Predictive-Search-Engine (3).html — predictive arc source`
- `Axiom-Dynamic-Data-Orchestration.html — data pixel arc source`
- `src/shaders/predictive-arc/predictiveArcRenderer.ts`
- `src/shaders/data-pixel-arc/dataPixelArcRenderer.ts`
- `src/shaders/neuform-isolated/sources/signal-particles.html`
- `src/shaders/neuform-isolated/sources/override-grid.html`
- `src/shaders/neuform-isolated/NeuformBatchEffects.tsx`
- `src/shaders/ribbon-field/RibbonFieldBackground.tsx`
- `src/shaders/ribbon-field/ribbonFieldShaders.ts`
- `src/shaders/neuform-isolated/NeuformIsolatedEffects.tsx`
- `src/shaders/neuform-isolated/sources/void-protocol.html`
- `src/shaders/neuform-isolated/NeuformCraftEffects.tsx`
- `src/shaders/neuform-isolated/sources/nexus-unified-flow.html`
- `src/shaders/neuform-isolated/sources/amber-halftone.html`
- `src/shaders/predictive-arc/PredictiveArcCollection.tsx`
- `src/shaders/predictive-arc/PredictiveArcCanvas.tsx`

Source revision: `SHA-256 fa86582fc870`

## Implementation steps

1. Open every verified source file listed above and identify the renderer, host lifecycle, styles, and assets before editing.
2. Keep Predictive Arc as the public entry point and select predictive, data-pixel, signal-particles, override-grid, ribbon-field, void-field, halftone-flow, or amber-halftone with the variant prop.
3. Retain each authored renderer and its original composition instead of blending the scenes into one canvas.
4. Expose the shared mode, speed, hue, saturation, and brightness controls at the collection boundary.
5. Lazy-load the isolated Signal Particles, Override Grid, Ribbon Field, Void Field, Halftone Flow, and Amber Halftone renderers so only the selected variant runs.
6. Preserve each renderer's resize, visibility, animation-frame, and cleanup lifecycle.
7. Give the local component a sized, overflow-controlled parent and verify desktop, mobile, reduced-motion, and context-loss behavior.

Asset handling: This effect has no required external assets.

## Local component example

Import the copied local component rather than a package entrypoint:

```tsx
import { PredictiveArcCanvas } from "./effects/predictive-arc/PredictiveArcCanvas";
import "./effects/predictive-arc/styles.css";

export function Scene() {
  return <div className="effect-frame"><PredictiveArcCanvas /></div>;
}
```

## Core renderer pattern

This excerpt documents orchestration only. Copy the exact shader, geometry, pass, and interaction code from the verified source files.

```tsx
<PredictiveArcCanvas variant="ribbon-field" speed={1.2} hue={12} />
```

## Behavior contract

- Runtime: Canvas 2D + Raw WebGL + Three.js r128
- Passes: 1 selected Canvas 2D, raw-WebGL, or Three.js field pass
- Interaction: Variant selection plus customizable mode, speed, color, and brightness
- Assets: No external assets
- **renderer** (host): Canvas 2D + Raw WebGL + Three.js
- **variants** (fixed): Predictive + Data Pixel + Signal + Override + Ribbon + Void + Halftone Flow + Amber Halftone
- **mode** (optional): dark | light
- **pixelRatio** (adaptive): ≤ 2
- **assets** (fixed): None

## Verification

1. Compare the rendered composition, animation timing, pointer behavior, and state transitions with the source implementation.
2. Exercise resize, high-DPI, mobile/coarse-pointer, reduced-motion, tab visibility, and WebGL context-loss paths where applicable.
3. Confirm every animation frame, observer, listener, geometry, buffer, texture, framebuffer, material, and renderer is released on teardown.
4. Check the browser console and confirm the effect renders at native-or-better backing resolution.

## Guardrails

- Do not substitute a visually similar package, demo, shader, or runtime.
- Do not approximate, reconstruct, or simplify the authored GLSL, render passes, geometry, interaction state, or assets.
- Keep exact source and asset hashes under regression tests when the source project provides them.
- Adapt only the surrounding host boundary needed by the target project; keep renderer behavior intact.


---
name: add-predictive-arc
description: "Build Predictive Arc from its verified authored source using Canvas 2D + Raw WebGL + Three.js r128, including the complete renderer, interactions, and required assets. Use when Codex needs to implement, port, or adapt this effect without requiring the ThreeUI package or reconstructing the visual from an approximation."
---

# Build Predictive Arc

## Description

Eight animated arc, signal, ribbon, void, and halftone scenes collected in one Canvas 2D, raw-WebGL, and Three.js family.

Recreate the authored behavior from the verified source, not from screenshots or the abbreviated orchestration sample in this skill. The implementation may live directly in the target project and does not require `@designcodeio/threeui`.

## Technologies

- React variant host
- Four Canvas 2D renderers
- Three raw-WebGL renderers
- One Three.js point-field renderer
- Dark/light mode surfaces
- Lazy-loaded variant sources
- ResizeObserver, IntersectionObserver, adaptive pixel ratio, and requestAnimationFrame

## Verified source material

- `Axiom---Predictive-Search-Engine (3).html — predictive arc source`
- `Axiom-Dynamic-Data-Orchestration.html — data pixel arc source`
- `src/shaders/predictive-arc/predictiveArcRenderer.ts`
- `src/shaders/data-pixel-arc/dataPixelArcRenderer.ts`
- `src/shaders/neuform-isolated/sources/signal-particles.html`
- `src/shaders/neuform-isolated/sources/override-grid.html`
- `src/shaders/neuform-isolated/NeuformBatchEffects.tsx`
- `src/shaders/ribbon-field/RibbonFieldBackground.tsx`
- `src/shaders/ribbon-field/ribbonFieldShaders.ts`
- `src/shaders/neuform-isolated/NeuformIsolatedEffects.tsx`
- `src/shaders/neuform-isolated/sources/void-protocol.html`
- `src/shaders/neuform-isolated/NeuformCraftEffects.tsx`
- `src/shaders/neuform-isolated/sources/nexus-unified-flow.html`
- `src/shaders/neuform-isolated/sources/amber-halftone.html`
- `src/shaders/predictive-arc/PredictiveArcCollection.tsx`
- `src/shaders/predictive-arc/PredictiveArcCanvas.tsx`

Source revision: `SHA-256 fa86582fc870`

## Implementation steps

1. Open every verified source file listed above and identify the renderer, host lifecycle, styles, and assets before editing.
2. Keep Predictive Arc as the public entry point and select predictive, data-pixel, signal-particles, override-grid, ribbon-field, void-field, halftone-flow, or amber-halftone with the variant prop.
3. Retain each authored renderer and its original composition instead of blending the scenes into one canvas.
4. Expose the shared mode, speed, hue, saturation, and brightness controls at the collection boundary.
5. Lazy-load the isolated Signal Particles, Override Grid, Ribbon Field, Void Field, Halftone Flow, and Amber Halftone renderers so only the selected variant runs.
6. Preserve each renderer's resize, visibility, animation-frame, and cleanup lifecycle.
7. Give the local component a sized, overflow-controlled parent and verify desktop, mobile, reduced-motion, and context-loss behavior.

Asset handling: This effect has no required external assets.

## Local component example

Import the copied local component rather than a package entrypoint:

```tsx
import { PredictiveArcCanvas } from "./effects/predictive-arc/PredictiveArcCanvas";
import "./effects/predictive-arc/styles.css";

export function Scene() {
  return <div className="effect-frame"><PredictiveArcCanvas /></div>;
}
```

## Core renderer pattern

This excerpt documents orchestration only. Copy the exact shader, geometry, pass, and interaction code from the verified source files.

```tsx
<PredictiveArcCanvas variant="ribbon-field" speed={1.2} hue={12} />
```

## Behavior contract

- Runtime: Canvas 2D + Raw WebGL + Three.js r128
- Passes: 1 selected Canvas 2D, raw-WebGL, or Three.js field pass
- Interaction: Variant selection plus customizable mode, speed, color, and brightness
- Assets: No external assets
- **renderer** (host): Canvas 2D + Raw WebGL + Three.js
- **variants** (fixed): Predictive + Data Pixel + Signal + Override + Ribbon + Void + Halftone Flow + Amber Halftone
- **mode** (optional): dark | light
- **pixelRatio** (adaptive): ≤ 2
- **assets** (fixed): None

## Verification

1. Compare the rendered composition, animation timing, pointer behavior, and state transitions with the source implementation.
2. Exercise resize, high-DPI, mobile/coarse-pointer, reduced-motion, tab visibility, and WebGL context-loss paths where applicable.
3. Confirm every animation frame, observer, listener, geometry, buffer, texture, framebuffer, material, and renderer is released on teardown.
4. Check the browser console and confirm the effect renders at native-or-better backing resolution.

## Guardrails

- Do not substitute a visually similar package, demo, shader, or runtime.
- Do not approximate, reconstruct, or simplify the authored GLSL, render passes, geometry, interaction state, or assets.
- Keep exact source and asset hashes under regression tests when the source project provides them.
- Adapt only the surrounding host boundary needed by the target project; keep renderer behavior intact.


---
name: add-predictive-arc
description: "Build Predictive Arc from its verified authored source using Canvas 2D + Raw WebGL + Three.js r128, including the complete renderer, interactions, and required assets. Use when Codex needs to implement, port, or adapt this effect without requiring the ThreeUI package or reconstructing the visual from an approximation."
---

# Build Predictive Arc

## Description

Eight animated arc, signal, ribbon, void, and halftone scenes collected in one Canvas 2D, raw-WebGL, and Three.js family.

Recreate the authored behavior from the verified source, not from screenshots or the abbreviated orchestration sample in this skill. The implementation may live directly in the target project and does not require `@designcodeio/threeui`.

## Technologies

- React variant host
- Four Canvas 2D renderers
- Three raw-WebGL renderers
- One Three.js point-field renderer
- Dark/light mode surfaces
- Lazy-loaded variant sources
- ResizeObserver, IntersectionObserver, adaptive pixel ratio, and requestAnimationFrame

## Verified source material

- `Axiom---Predictive-Search-Engine (3).html — predictive arc source`
- `Axiom-Dynamic-Data-Orchestration.html — data pixel arc source`
- `src/shaders/predictive-arc/predictiveArcRenderer.ts`
- `src/shaders/data-pixel-arc/dataPixelArcRenderer.ts`
- `src/shaders/neuform-isolated/sources/signal-particles.html`
- `src/shaders/neuform-isolated/sources/override-grid.html`
- `src/shaders/neuform-isolated/NeuformBatchEffects.tsx`
- `src/shaders/ribbon-field/RibbonFieldBackground.tsx`
- `src/shaders/ribbon-field/ribbonFieldShaders.ts`
- `src/shaders/neuform-isolated/NeuformIsolatedEffects.tsx`
- `src/shaders/neuform-isolated/sources/void-protocol.html`
- `src/shaders/neuform-isolated/NeuformCraftEffects.tsx`
- `src/shaders/neuform-isolated/sources/nexus-unified-flow.html`
- `src/shaders/neuform-isolated/sources/amber-halftone.html`
- `src/shaders/predictive-arc/PredictiveArcCollection.tsx`
- `src/shaders/predictive-arc/PredictiveArcCanvas.tsx`

Source revision: `SHA-256 fa86582fc870`

## Implementation steps

1. Open every verified source file listed above and identify the renderer, host lifecycle, styles, and assets before editing.
2. Keep Predictive Arc as the public entry point and select predictive, data-pixel, signal-particles, override-grid, ribbon-field, void-field, halftone-flow, or amber-halftone with the variant prop.
3. Retain each authored renderer and its original composition instead of blending the scenes into one canvas.
4. Expose the shared mode, speed, hue, saturation, and brightness controls at the collection boundary.
5. Lazy-load the isolated Signal Particles, Override Grid, Ribbon Field, Void Field, Halftone Flow, and Amber Halftone renderers so only the selected variant runs.
6. Preserve each renderer's resize, visibility, animation-frame, and cleanup lifecycle.
7. Give the local component a sized, overflow-controlled parent and verify desktop, mobile, reduced-motion, and context-loss behavior.

Asset handling: This effect has no required external assets.

## Local component example

Import the copied local component rather than a package entrypoint:

```tsx
import { PredictiveArcCanvas } from "./effects/predictive-arc/PredictiveArcCanvas";
import "./effects/predictive-arc/styles.css";

export function Scene() {
  return <div className="effect-frame"><PredictiveArcCanvas /></div>;
}
```

## Core renderer pattern

This excerpt documents orchestration only. Copy the exact shader, geometry, pass, and interaction code from the verified source files.

```tsx
<PredictiveArcCanvas variant="ribbon-field" speed={1.2} hue={12} />
```

## Behavior contract

- Runtime: Canvas 2D + Raw WebGL + Three.js r128
- Passes: 1 selected Canvas 2D, raw-WebGL, or Three.js field pass
- Interaction: Variant selection plus customizable mode, speed, color, and brightness
- Assets: No external assets
- **renderer** (host): Canvas 2D + Raw WebGL + Three.js
- **variants** (fixed): Predictive + Data Pixel + Signal + Override + Ribbon + Void + Halftone Flow + Amber Halftone
- **mode** (optional): dark | light
- **pixelRatio** (adaptive): ≤ 2
- **assets** (fixed): None

## Verification

1. Compare the rendered composition, animation timing, pointer behavior, and state transitions with the source implementation.
2. Exercise resize, high-DPI, mobile/coarse-pointer, reduced-motion, tab visibility, and WebGL context-loss paths where applicable.
3. Confirm every animation frame, observer, listener, geometry, buffer, texture, framebuffer, material, and renderer is released on teardown.
4. Check the browser console and confirm the effect renders at native-or-better backing resolution.

## Guardrails

- Do not substitute a visually similar package, demo, shader, or runtime.
- Do not approximate, reconstruct, or simplify the authored GLSL, render passes, geometry, interaction state, or assets.
- Keep exact source and asset hashes under regression tests when the source project provides them.
- Adapt only the surrounding host boundary needed by the target project; keep renderer behavior intact.


---
name: add-star-portal
description: "Build Shader Buttons from its verified authored source using Raw WebGL + WebGL2 + Three.js + Canvas 2D + CSS, including the complete renderer, interactions, and required assets. Use when Codex needs to implement, port, or adapt this effect without requiring the ThreeUI package or reconstructing the visual from an approximation."
---

# Build Shader Buttons

## Description

Interactive shader, canvas, and material buttons with authored hover and press states.

Recreate the authored behavior from the verified source, not from screenshots or the abbreviated orchestration sample in this skill. The implementation may live directly in the target project and does not require `@designcodeio/threeui`.

## Technologies

- React variant host
- Five raw WebGL button sources
- Four Canvas 2D button sources
- WebGL2 and Three.js button studies
- Authored CSS controls
- Lazy-loaded isolated renderers

## Verified source material

- `src/shaders/shader-buttons/ShaderButtons.tsx`
- `src/shaders/shader-buttons/RakingLightPillButton.tsx`
- `src/shaders/neuform-isolated/NeuformIsolatedEffects.tsx`
- `src/shaders/neuform-isolated/sources/imaginie-starfield.html`
- `src/shaders/neuform-isolated/sources/ignition-terminal.html`
- `src/shaders/neuform-isolated/sources/valence-core.html`
- `src/shaders/neuform-isolated/sources/aetheris-labs.html`
- `src/shaders/neuform-isolated/sources/nexus-tactile.html`
- `src/shaders/neuform-isolated/sources/thinking-button.html`
- `src/shaders/shader-buttons/SelectedButtonStudies.tsx`
- `src/shaders/shader-buttons/sources/button-index.html`

Source revision: `SHA-256 6f56c4f91814`

## Implementation steps

1. Open every verified source file listed above and identify the renderer, host lifecycle, styles, and assets before editing.
2. Keep ShaderButtons as the public entry point. The original seven variants remain available, and liquid-glass, intelligence, holo-foil, particles, voice-orb, water, dither-hold, lava-lamp, gold, and ink are Pro variants.
3. Retain the original source documents, the self-contained Raking Light Pill shader, and the exact owner-supplied ten-study HTML. Render only the selected study in its sandboxed frame.
4. Expose mode and palette controls at the family boundary while leaving each button's authored behavior intact.
5. Lazy-load and mount only the selected button renderer so inactive variants do not allocate canvases, WebGL contexts, or animation loops.
6. Give the local component a sized, overflow-controlled parent and verify desktop, mobile, reduced-motion, and context-loss behavior.

Asset handling: This effect has no required external assets.

## Local component example

Import the copied local component rather than a package entrypoint:

```tsx
import { ShaderButtons } from "./effects/star-portal/ShaderButtons";
import "./effects/star-portal/styles.css";

export function Scene() {
  return <div className="effect-frame"><ShaderButtons /></div>;
}
```

## Core renderer pattern

This excerpt documents orchestration only. Copy the exact shader, geometry, pass, and interaction code from the verified source files.

```tsx
<ShaderButtons variant="raking-light-pill" mode="dark" />
```

## Behavior contract

- Runtime: Raw WebGL + WebGL2 + Three.js + Canvas 2D + CSS
- Passes: 1 selected shader, canvas, and CSS button composition, including WebGL2 fluid studies
- Interaction: Variant selection with authored pointer, hover, motion, and palette behavior
- Assets: No owned binary assets
- **source** (fixed): Exact Neuform and owner-supplied Shader Buttons HTML
- **focus** (host): Effect-only sandbox
- **mode** (optional): dark | light
- **palette** (optional): Final-frame grade
- **assets** (fixed): No owned binary assets
- **variants** (fixed): Shader, canvas, material, and Pro button studies

## Verification

1. Compare the rendered composition, animation timing, pointer behavior, and state transitions with the source implementation.
2. Exercise resize, high-DPI, mobile/coarse-pointer, reduced-motion, tab visibility, and WebGL context-loss paths where applicable.
3. Confirm every animation frame, observer, listener, geometry, buffer, texture, framebuffer, material, and renderer is released on teardown.
4. Check the browser console and confirm the effect renders at native-or-better backing resolution.

## Guardrails

- Do not substitute a visually similar package, demo, shader, or runtime.
- Do not approximate, reconstruct, or simplify the authored GLSL, render passes, geometry, interaction state, or assets.
- Keep exact source and asset hashes under regression tests when the source project provides them.
- Adapt only the surrounding host boundary needed by the target project; keep renderer behavior intact.


---
name: add-rectangle-buttons
description: "Build Rectangle Buttons from its verified authored source using DOM + CSS, including the complete renderer, interactions, and required assets. Use when Codex needs to implement, port, or adapt this effect without requiring the ThreeUI package or reconstructing the visual from an approximation."
---

# Build Rectangle Buttons

## Description

Twenty-four authored rectangle-button and animated CTA treatments collected into one family.

Recreate the authored behavior from the verified source, not from screenshots or the abbreviated orchestration sample in this skill. The implementation may live directly in the target project and does not require `@designcodeio/threeui`.

## Technologies

- React variant host
- One Section DOM/CSS source
- Ten isolated DOM/CSS CTA sources
- Two Lumen DOM/CSS treatments
- Eleven selected page-button treatments
- Light and dark palette controls
- Lazy-loaded variant renderers

## Verified source material

- `src/shaders/rectangle-buttons/RectangleButtons.tsx`
- `remote-control.html — shared button treatment`
- `src/shaders/section-elements/SectionElements.tsx`
- `src/shaders/section-elements/section-elements.css`
- `src/shaders/neuform-isolated/NeuformIsolatedEffects.tsx`
- `src/shaders/neuform-isolated/sources/launch-button.html`
- `src/shaders/neuform-isolated/sources/dot-border-button.html`
- `src/shaders/neuform-isolated/sources/floating-dots-cta.html`
- `src/shaders/neuform-isolated/sources/sliding-text-cta.html`
- `src/shaders/neuform-isolated/sources/gradient-beam-cta.html`
- `src/shaders/neuform-isolated/sources/gradient-pill-button.html`
- `src/shaders/neuform-isolated/sources/generate-button.html`
- `src/shaders/neuform-isolated/sources/glassmorphism-cta.html`
- `src/shaders/neuform-isolated/sources/spinning-border-button.html`
- `src/shaders/neuform-isolated/sources/gradient-cta.html`
- `src/shaders/lumen-cta/LumenCta.tsx`
- `src/shaders/lumen-cta/lumen-cta.css`
- `src/shaders/lumen-cta/sources/lumen.html`
- `halftone-bloom.html — Aster glass access and arrow CTA treatments`
- `public/landing-pages/cinder-k1-hero.html — Cinder K1 pre-order keycap treatment`
- `public/landing-pages/hanami.html — See the season outline CTA treatment`

Source revision: `SHA-256 ff30e28c2781`

## Implementation steps

1. Open every verified source file listed above and identify the renderer, host lifecycle, styles, and assets before editing.
2. Keep RectangleButtons as the public entry point and select any catalog treatment with the variant prop, including ember-keycap for the glowing tactile keycap or bloom-outline-button for the magnetic ink-bloom outline CTA.
3. Retain the original dark-glass rectangle, all ten complete authored CTA documents, and both Lumen treatments instead of flattening their markup or animation systems.
4. Expose mode and palette controls at the collection boundary while leaving each variant's authored hover, focus, and motion behavior intact.
5. Lazy-load and mount only the selected CTA renderer so inactive variants do not allocate isolated documents or animation loops.
6. Give the local component a sized, overflow-controlled parent and verify desktop, mobile, reduced-motion, and context-loss behavior.

Asset handling: This effect has no required external assets.

## Local component example

Import the copied local component rather than a package entrypoint:

```tsx
import { RectangleButtons } from "./effects/rectangle-buttons/RectangleButtons";
import "./effects/rectangle-buttons/styles.css";

export function Scene() {
  return <div className="effect-frame"><RectangleButtons /></div>;
}
```

## Core renderer pattern

This excerpt documents orchestration only. Copy the exact shader, geometry, pass, and interaction code from the verified source files.

```tsx
<RectangleButtons variant="bloom-outline-button" mode="dark" />
```

## Behavior contract

- Runtime: DOM + CSS
- Passes: 1 selected DOM/CSS button composition
- Interaction: Variant selection with authored hover, focus, motion, and palette behavior
- Assets: 5 local SF Pro font subsets + 1 authored remote portrait reference
- **renderer** (host): React DOM + scoped CSS
- **source** (fixed): Owner-selected reference HTML
- **theme** (fixed): Dark
- **layout** (responsive): Container-relative 16:9 composition
- **motion** (adaptive): Reduced-motion safe
- **assets** (owned): Local fonts and illustrations
- **variants** (fixed): Dark Glass + Launch + Dot Border + Floating Dots + Sliding Text + Gradient Beam + Gradient Pill + Generate + Glassmorphism + Spinning Border + Gradient + Lumen CTA + Lumen CTA Ghost + Trochil Signal + Attune Thermal + Tideform Outline + Understory Arrow Pill + Meridian Keycap Primary + Meridian Keycap Secondary + Halvorsen Arrow Pill + Aster Glass Access + Aster Glass Arrow + Ember Keycap + Bloom Outline Button

## Verification

1. Compare the rendered composition, animation timing, pointer behavior, and state transitions with the source implementation.
2. Exercise resize, high-DPI, mobile/coarse-pointer, reduced-motion, tab visibility, and WebGL context-loss paths where applicable.
3. Confirm every animation frame, observer, listener, geometry, buffer, texture, framebuffer, material, and renderer is released on teardown.
4. Check the browser console and confirm the effect renders at native-or-better backing resolution.

## Guardrails

- Do not substitute a visually similar package, demo, shader, or runtime.
- Do not approximate, reconstruct, or simplify the authored GLSL, render passes, geometry, interaction state, or assets.
- Keep exact source and asset hashes under regression tests when the source project provides them.
- Adapt only the surrounding host boundary needed by the target project; keep renderer behavior intact.


---
name: add-liquid-metal-button
description: "Build Liquid Metal Button from its verified authored source using Raw WebGL 2 + DOM/CSS, including the complete renderer, interactions, and required assets. Use when Codex needs to implement, port, or adapt this effect without requiring the ThreeUI package or reconstructing the visual from an approximation."
---

# Build Liquid Metal Button

## Description

A prismatic liquid-metal control in Sign up pill, Liquid Orb, and configurable Play Circle variants, with pointer-following bloom and press ripples.

Recreate the authored behavior from the verified source, not from screenshots or the abbreviated orchestration sample in this skill. The implementation may live directly in the target project and does not require `@designcodeio/threeui`.

## Technologies

- React and TypeScript visibility-aware sandbox host
- Exact self-contained raw WebGL2, DOM, and CSS document imported as source text
- Semantic native button with authored hover, focus, pressed, and keyboard states
- Multipass spectral metal, crisp rim, adaptive softening, multi-radius bloom, and composite pipeline
- Configurable circular play variant with live finish, diameter, stroke, and accessible-label controls
- Pointer-dragged liquid field, faceted press ripples, capped DPR, and reduced-motion freezing

## Verified source material

- `src/shaders/liquid-metal-button/liquid-metal-button.html`
- `src/shaders/liquid-metal-button/LiquidMetalButton.tsx`

Source revision: `SHA-256 76624e881a3a`

## Implementation steps

1. Open every verified source file listed above and identify the renderer, host lifecycle, styles, and assets before editing.
2. Keep the complete authored HTML byte-for-byte; do not rewrite its shaders, framebuffer graph, CSS plate, button semantics, interaction state, or tuning hooks.
3. Import the canonical document as a raw string and mount it through an `allow-scripts`-only srcDoc iframe so its WebGL2 and DOM event scopes remain isolated.
4. Select the authored Sign up pill with `variant="pill"`, the compact Liquid Orb with `variant="circle"`, or the configurable play control with `variant="play"`.
5. Let the source-owned CSS size the pill responsively, keep the orb at 56–72px, and let the renderer cap backing resolution at 2× device pixel ratio.
6. Select the play variant to map equal width and height into the same pill SDF, then update diameter, rim width, colored or monotone finish, and the icon-only control's accessible name through the iframe message adapter without remounting it.
7. Retain pointer hover and drag, pointer and keyboard ripple launches, focus-visible styling, and the source-owned reduced-motion clock freeze.
8. Unmount the iframe when the host is offscreen or the document is hidden so its WebGL context, buffers, framebuffers, listeners, and animation loop are released together.
9. Give the local component a sized, overflow-controlled parent and verify desktop, mobile, reduced-motion, and context-loss behavior.

Asset handling: This effect has no required external assets.

## Local component example

Import the copied local component rather than a package entrypoint:

```tsx
import { LiquidMetalButton } from "./effects/liquid-metal-button/LiquidMetalButton";
import "./effects/liquid-metal-button/styles.css";

export function Scene() {
  return <div className="effect-frame"><LiquidMetalButton /></div>;
}
```

## Core renderer pattern

This excerpt documents orchestration only. Copy the exact shader, geometry, pass, and interaction code from the verified source files.

```tsx
<LiquidMetalButton variant="play" rendering="colored" diameter={88} strokeWidth={3} text="Play" />
```

## Behavior contract

- Runtime: Raw WebGL 2 + DOM/CSS
- Passes: Up to 20 — metal, crisp rim, adaptive softening, multi-radius bloom, and composite
- Interaction: Hover, focus, pointer-dragged metal, faceted press ripples, and Enter/Space activation
- Assets: 1 exact authored HTML scene with remote Inter stylesheet and system-font fallback
- **renderer** (sandbox): Raw WebGL 2 + DOM/CSS
- **control** (semantic): Native button
- **variants** (fixed): Sign up Pill + Liquid Orb + configurable Play Circle
- **geometry** (optional): 72–160 px circle + 1–8 px stroke
- **appearance** (optional): Colored | monotone
- **content** (optional): Custom accessible name
- **metal** (fixed): Spectral dispersion field
- **post** (adaptive): Softening + bloom
- **interaction** (pointer): Hover + drag + ripple
- **pixelRatio** (adaptive): ≤ 2
- **motion** (adaptive): Reduced-motion freeze
- **assets** (external): Inter stylesheet + fallback

## Verification

1. Compare the rendered composition, animation timing, pointer behavior, and state transitions with the source implementation.
2. Exercise resize, high-DPI, mobile/coarse-pointer, reduced-motion, tab visibility, and WebGL context-loss paths where applicable.
3. Confirm every animation frame, observer, listener, geometry, buffer, texture, framebuffer, material, and renderer is released on teardown.
4. Check the browser console and confirm the effect renders at native-or-better backing resolution.

## Guardrails

- Do not substitute a visually similar package, demo, shader, or runtime.
- Do not approximate, reconstruct, or simplify the authored GLSL, render passes, geometry, interaction state, or assets.
- Keep exact source and asset hashes under regression tests when the source project provides them.
- Adapt only the surrounding host boundary needed by the target project; keep renderer behavior intact.


---
name: add-circle-buttons
description: "Build Circle Buttons from its verified authored source using DOM + CSS, including the complete renderer, interactions, and required assets. Use when Codex needs to implement, port, or adapt this effect without requiring the ThreeUI package or reconstructing the visual from an approximation."
---

# Build Circle Buttons

## Description

Three compact circular icon controls using the exact Dark Glass, Launch, and Dot Border material systems.

Recreate the authored behavior from the verified source, not from screenshots or the abbreviated orchestration sample in this skill. The implementation may live directly in the target project and does not require `@designcodeio/threeui`.

## Technologies

- React and TypeScript
- Semantic button elements
- Scoped layered CSS
- Inline SVG icons
- Light and dark palette controls
- Reduced-motion fallback

## Verified source material

- `src/shaders/circle-buttons/CircleButtons.tsx`
- `src/shaders/circle-buttons/circle-buttons.css`

Source revision: `SHA-256 2e85693f7ada`

## Implementation steps

1. Open every verified source file listed above and identify the renderer, host lifecycle, styles, and assets before editing.
2. Use CircleButtons as the public entry point and select play, plus, or mail with the variant prop.
3. Keep every variant circular, icon-only, and compact at its responsive 56–72px default; provide ariaLabel when the surrounding action needs a more specific accessible name.
4. Map each treatment directly to its Rectangle Buttons source: Dark Glass for Play, Launch for Plus, and Dot Border for Mail, including the original material tokens and motion timing.
5. Keep hover, keyboard focus, pressed, disabled, and reduced-motion behavior intact when adapting the control to another layout.
6. Use mode and palette controls at the component boundary rather than rewriting the internal highlight and shadow layers.
7. Give the local component a sized, overflow-controlled parent and verify desktop, mobile, reduced-motion, and context-loss behavior.

Asset handling: This effect has no required external assets.

## Local component example

Import the copied local component rather than a package entrypoint:

```tsx
import { CircleButtons } from "./effects/circle-buttons/CircleButtons";
import "./effects/circle-buttons/styles.css";

export function Scene() {
  return <div className="effect-frame"><CircleButtons /></div>;
}
```

## Core renderer pattern

This excerpt documents orchestration only. Copy the exact shader, geometry, pass, and interaction code from the verified source files.

```tsx
<CircleButtons variant="mail" mode="dark" ariaLabel="Open inbox" />
```

## Behavior contract

- Runtime: DOM + CSS
- Passes: 1 layered DOM/CSS circle composition
- Interaction: Source-faithful hover and press behavior, focus-visible ring, reduced-motion fallback, and adaptive light/dark palette
- Assets: Inline SVG icons; no external runtime assets
- **renderer** (host): Semantic button + scoped layered CSS
- **variants** (fixed): Play + Plus + Mail
- **materials** (fixed): Dark Glass + Launch + Dot Border
- **size** (responsive): 56–72px diameter
- **theme** (adaptive): Dark (default) | Light
- **interaction** (adaptive): Hover | Focus | Press | Disabled | Reduced motion
- **assets** (embedded): Three inline SVG icons

## Verification

1. Compare the rendered composition, animation timing, pointer behavior, and state transitions with the source implementation.
2. Exercise resize, high-DPI, mobile/coarse-pointer, reduced-motion, tab visibility, and WebGL context-loss paths where applicable.
3. Confirm every animation frame, observer, listener, geometry, buffer, texture, framebuffer, material, and renderer is released on teardown.
4. Check the browser console and confirm the effect renders at native-or-better backing resolution.

## Guardrails

- Do not substitute a visually similar package, demo, shader, or runtime.
- Do not approximate, reconstruct, or simplify the authored GLSL, render passes, geometry, interaction state, or assets.
- Keep exact source and asset hashes under regression tests when the source project provides them.
- Adapt only the surrounding host boundary needed by the target project; keep renderer behavior intact.


---
name: add-article-headings
description: "Build Article Headings from its verified authored source using DOM/CSS + Canvas 2D, including the complete renderer, interactions, and required assets. Use when Codex needs to implement, port, or adapt this effect without requiring the ThreeUI package or reconstructing the visual from an approximation."
---

# Build Article Headings

## Description

Three expressive text treatments collected in one family: a chromatic intro, a particle wordmark, and an audio-reactive identity lockup.

Recreate the authored behavior from the verified source, not from screenshots or the abbreviated orchestration sample in this skill. The implementation may live directly in the target project and does not require `@designcodeio/threeui`.

## Technologies

- A lazy React and TypeScript host for five text-animation variants
- Semantic DOM headings with requestAnimationFrame decoding
- Canvas 2D neon, particle-mask, and audio-bar renderers
- A chromatic DOM/CSS intro isolated from its authored source document
- Synchronized dark/light surfaces, palette controls, and reduced-motion handling

## Verified source material

- `ascii-page-transition-v1.html — article headings and decode lifecycle`
- `src/shaders/article-headings/TextAnimationCollection.tsx`
- `src/shaders/article-headings/articleHeadingDecode.ts`
- `src/shaders/article-headings/ArticleHeadings.tsx`
- `src/shaders/neuform-isolated/sources/glassblown-neon.html`
- `src/shaders/neuform-isolated/sources/creator-studio-intro.html`
- `src/shaders/neuform-isolated/sources/epilude-footer.html`
- `src/shaders/neuform-isolated/sources/audio-wordmark.html`
- `src/shaders/neuform-isolated/NeuformCraftEffects.tsx`
- `src/shaders/neuform-isolated/NeuformIsolatedEffects.tsx`
- `src/shaders/fonts/fragment-mono.woff2`

Source revision: `5a736cd3c1f6f19802f61ebb10e1701b9f7aa26e / SHA-256 e14795f24ea8 / 8d2cfccf1140 / 26f0d8d04494 / 1545c354af8d`

## Implementation steps

1. Open every verified source file listed above and identify the renderer, host lifecycle, styles, and assets before editing.
2. Expose article-headings, neon-sign, threeui-intro, particle-wordmark, and audio-wordmark through one discriminated variant prop.
3. Preserve the article decoder as semantic headings, including its eased reveal budget, scramble window, cleanup, and reduced-motion behavior.
4. Keep the Neon Typography source and its Canvas 2D tubing, electrode, flicker, and bloom renderer intact.
5. Keep the intro, particle, and audio documents as sandboxed authored sources, adapting only presentation, theme, and ThreeUI copy.
6. Lazy-load each renderer, forward only its compatible props, and preserve the family’s per-variant control sets and preview media.
7. Give the local component a sized, overflow-controlled parent and verify desktop, mobile, reduced-motion, and context-loss behavior.

Asset handling: Copy the exact extracted Fragment Mono file for the article metadata and keep the four bundled owned HTML source documents available to the collection adapters.

## Local component example

Import the copied local component rather than a package entrypoint:

```tsx
import { TextAnimationCollection } from "./effects/article-headings/TextAnimationCollection";
import "./effects/article-headings/styles.css";

export function Scene() {
  return <div className="effect-frame"><TextAnimationCollection variant="article-headings" mode="dark" duration={560} stagger={140} /></div>;
}
```

## Core renderer pattern

This excerpt documents orchestration only. Copy the exact shader, geometry, pass, and interaction code from the verified source files.

```tsx
<TextAnimationCollection variant="audio-wordmark" mode="dark" brightness={1} />
```

## Behavior contract

- Runtime: DOM/CSS + Canvas 2D
- Passes: Variant-dependent DOM/CSS or one to two Canvas 2D passes
- Interaction: Authored text motion with responsive presentation, reduced-motion handling, and synchronized light/dark mode
- Assets: Exact embedded Fragment Mono font; all other sources and marks are bundled inline
- **renderer** (variant): DOM/CSS or Canvas 2D
- **variants** (fixed): Intro | Particle | Audio
- **mode** (optional): dark | light
- **motion** (adaptive): Reduced-motion aware
- **assets** (bundled): Fragment Mono + inline source documents

## Verification

1. Compare the rendered composition, animation timing, pointer behavior, and state transitions with the source implementation.
2. Exercise resize, high-DPI, mobile/coarse-pointer, reduced-motion, tab visibility, and WebGL context-loss paths where applicable.
3. Confirm every animation frame, observer, listener, geometry, buffer, texture, framebuffer, material, and renderer is released on teardown.
4. Check the browser console and confirm the effect renders at native-or-better backing resolution.

## Guardrails

- Do not substitute a visually similar package, demo, shader, or runtime.
- Do not approximate, reconstruct, or simplify the authored GLSL, render passes, geometry, interaction state, or assets.
- Keep exact source and asset hashes under regression tests when the source project provides them.
- Adapt only the surrounding host boundary needed by the target project; keep renderer behavior intact.


---
name: add-skeuomorphic-toggle
description: "Build Skeuomorphic Toggle from its verified authored source using DOM/CSS + Three.js + Raw WebGL, including the complete renderer, interactions, and required assets. Use when Codex needs to implement, port, or adapt this effect without requiring the ThreeUI package or reconstructing the visual from an approximation."
---

# Build Skeuomorphic Toggle

## Description

Four takes on one switch: the preserved tactile skeuomorphic export plus flat modern, Three.js glass, and shader-lit treatments, each matching light and dark appearances automatically.

Recreate the authored behavior from the verified source, not from screenshots or the abbreviated orchestration sample in this skill. The implementation may live directly in the target project and does not require `@designcodeio/threeui`.

## Technologies

- React component with a sandboxed `srcDoc` effect boundary
- DOM/CSS copied from the byte-exact Neuform export
- A post-load focus adapter that keeps only the authored shader, button, canvas, or visual targets visible
- Optional outer-frame hue, saturation, and brightness grading with source-exact defaults

## Verified source material

- `src/shaders/neuform-isolated/sources/skeuomorphic-toggle.html`
- `src/shaders/neuform-isolated/NeuformBatchEffects.tsx`
- `src/shaders/skeuomorphic-toggle/SkeuomorphicToggleCollection.tsx`
- `src/shaders/skeuomorphic-toggle/ModernToggle.tsx`
- `src/shaders/skeuomorphic-toggle/GlassToggle.tsx`
- `src/shaders/skeuomorphic-toggle/glassToggleScene.ts`
- `src/shaders/skeuomorphic-toggle/ShaderToggle.tsx`
- `src/shaders/skeuomorphic-toggle/shaderToggleScene.ts`
- `src/shaders/skeuomorphic-toggle/shaderToggleGlsl.ts`
- `src/shaders/skeuomorphic-toggle/toggleMode.ts`

Source revision: `SHA-256 3e19e7fec9ac`

## Implementation steps

1. Open every verified source file listed above and identify the renderer, host lifecycle, styles, and assets before editing.
2. Copy the complete canonical HTML source byte-for-byte so its shader strings, materials, DOM, timing, and initialization order remain auditable.
3. After the source load event, retain only the #skeuomorphic-toggle control; do not rewrite the renderer or approximate the composition.
4. Force retained background targets to the sandbox viewport and center retained buttons without changing their internal pointer or shader state.
5. Dispatch one resize event after reparenting so the exact source renderer recalculates its backing resolution.
6. Apply optional hue, saturation, and brightness only to the outer iframe; omit the filter at 0/1/1 so source color remains exact.
7. Keep the sandbox isolated with `allow-scripts` only; removing the iframe must release its document, listeners, frames, and graphics contexts together.
8. Give the local component a sized, overflow-controlled parent and verify desktop, mobile, reduced-motion, and context-loss behavior.

Asset handling: This effect has no required external assets.

## Local component example

Import the copied local component rather than a package entrypoint:

```tsx
import { SkeuomorphicToggleCollection } from "./effects/skeuomorphic-toggle/SkeuomorphicToggleCollection";
import "./effects/skeuomorphic-toggle/styles.css";

export function Scene() {
  return <div className="effect-frame"><SkeuomorphicToggleCollection /></div>;
}
```

## Core renderer pattern

This excerpt documents orchestration only. Copy the exact shader, geometry, pass, and interaction code from the verified source files.

```tsx
const focusedSource = canonicalHtml
  .replace("</head>", focusStyles + "</head>")
  .replace("</body>", focusAfterLoadScript + "</body>");

return <iframe title="Focused source effect" srcDoc={focusedSource} sandbox="allow-scripts" />;
```

## Behavior contract

- Runtime: DOM/CSS + Three.js + Raw WebGL
- Passes: 1 selected toggle pass
- Interaction: Click or keyboard switching, pointer-lit 3D variants, automatic site/system appearance with explicit light and dark overrides, plus customizable speed, size, opacity, and palette
- Assets: No owned binary assets
- **source** (fixed): Exact Neuform HTML
- **focus** (host): Effect-only sandbox
- **mode** (optional): auto | dark | light
- **speed** (number): 1
- **size** (number): 1
- **length** (number): 1
- **density** (number): 1
- **opacity** (number): 1
- **palette** (optional): Final-frame grade
- **assets** (fixed): No owned binary assets

## Verification

1. Compare the rendered composition, animation timing, pointer behavior, and state transitions with the source implementation.
2. Exercise resize, high-DPI, mobile/coarse-pointer, reduced-motion, tab visibility, and WebGL context-loss paths where applicable.
3. Confirm every animation frame, observer, listener, geometry, buffer, texture, framebuffer, material, and renderer is released on teardown.
4. Check the browser console and confirm the effect renders at native-or-better backing resolution.

## Guardrails

- Do not substitute a visually similar package, demo, shader, or runtime.
- Do not approximate, reconstruct, or simplify the authored GLSL, render passes, geometry, interaction state, or assets.
- Keep exact source and asset hashes under regression tests when the source project provides them.
- Adapt only the surrounding host boundary needed by the target project; keep renderer behavior intact.


---
name: add-animated-top-dock
description: "Build Animated Top Dock from its verified authored source using DOM + CSS + WebGL + Three.js r128, including the complete renderer, interactions, and required assets. Use when Codex needs to implement, port, or adapt this effect without requiring the ThreeUI package or reconstructing the visual from an approximation."
---

# Build Animated Top Dock

## Description

Sable’s proximity-spring menu in four fits: the authored centred dock, a modern command bar, a fitted pixel-terminal strip, and a vertical refracting Three.js glass rail.

Recreate the authored behavior from the verified source, not from screenshots or the abbreviated orchestration sample in this skill. The implementation may live directly in the target project and does not require `@designcodeio/threeui`.

## Technologies

- Semantic nav and button controls with authored inline SVG icons
- Scoped glass CSS with backdrop filtering and active/focus states
- Per-item spring integration driven by horizontal pointer proximity
- ResizeObserver, fine-pointer capability checks, keyboard focus, and reduced motion
- The exact embedded Fragment Mono font for dock labels

## Verified source material

- `ascii-page-transition-v1.html — exact top menu dock`
- `src/shaders/animated-top-dock/topDockController.ts`
- `src/shaders/animated-top-dock/AnimatedTopDock.tsx`
- `src/shaders/animated-top-dock/retroPixelField.ts`
- `src/shaders/animated-top-dock/glassParticleField.ts`
- `src/shaders/fonts/fragment-mono.woff2`

Source revision: `5a736cd3c1f6f19802f61ebb10e1701b9f7aa26e`

## Implementation steps

1. Open every verified source file listed above and identify the renderer, host lifecycle, styles, and assets before editing.
2. Build one logo control and the five authored SYSTEM, METHOD, WORK, ACCESS, and NOTES items with the source icon geometry.
3. Measure each item at rest, then compute a smoothstep influence from pointer distance using the authored 122 px proximity radius.
4. Integrate each item toward its target with spring 0.19 and damping 0.70, applying at most 17 px width, 16 px height, and 3.5 px downward growth.
5. Mirror pointer proximity for keyboard focus, retain the selected-item paper state, and reset cleanly when focus or pointer leaves.
6. Disable resizing motion on coarse pointers, narrow screens, and reduced-motion systems while keeping the nav fully usable.
7. Re-measure on resize and remove all observers, listeners, media-query handlers, and animation frames on teardown.
8. Give the local component a sized, overflow-controlled parent and verify desktop, mobile, reduced-motion, and context-loss behavior.

Asset handling: Copy the exact extracted Fragment Mono file for the dock labels; all SVG menu icons are inline and require no other assets.

## Local component example

Import the copied local component rather than a package entrypoint:

```tsx
import { AnimatedTopDock } from "./effects/animated-top-dock/AnimatedTopDock";
import "./effects/animated-top-dock/styles.css";

export function Scene() {
  return <div className="effect-frame"><AnimatedTopDock proximity={122} spring={0.19} damping={0.7} /></div>;
}
```

## Core renderer pattern

This excerpt documents orchestration only. Copy the exact shader, geometry, pass, and interaction code from the verified source files.

```tsx
const influence = smoothstep(clamp(1 - distance / 122, 0, 1));
state.velocity += (influence - state.value) * 0.19;
state.velocity *= 0.70;
state.value += state.velocity;
item.style.transform = `translateY(${state.value * 3.5}px)`;
```

## Behavior contract

- Runtime: DOM + CSS + WebGL + Three.js r128
- Passes: 1 spring layout pass across every dock item, plus 1 shader pass on the pixel and glass variants
- Interaction: Pointer proximity, keyboard focus, active selection, pointer parallax, reduced motion, and mobile static mode
- Assets: Exact embedded Fragment Mono font extracted from the authored source
- **renderer** (variant): DOM + CSS, raw WebGL, or Three.js r128
- **variant** (optional): sable | modern | retro | glass
- **fit** (variant): centred | horizontal | vertical
- **items** (fixed): 1 brand + 5 menu items
- **proximity** (default): 122 px
- **spring** (default): 0.19 / 0.70
- **motion** (adaptive): Pointer + focus + reduced motion

## Verification

1. Compare the rendered composition, animation timing, pointer behavior, and state transitions with the source implementation.
2. Exercise resize, high-DPI, mobile/coarse-pointer, reduced-motion, tab visibility, and WebGL context-loss paths where applicable.
3. Confirm every animation frame, observer, listener, geometry, buffer, texture, framebuffer, material, and renderer is released on teardown.
4. Check the browser console and confirm the effect renders at native-or-better backing resolution.

## Guardrails

- Do not substitute a visually similar package, demo, shader, or runtime.
- Do not approximate, reconstruct, or simplify the authored GLSL, render passes, geometry, interaction state, or assets.
- Keep exact source and asset hashes under regression tests when the source project provides them.
- Adapt only the surrounding host boundary needed by the target project; keep renderer behavior intact.
