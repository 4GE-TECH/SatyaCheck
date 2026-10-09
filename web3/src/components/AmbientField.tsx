import { useEffect, useRef } from 'react';

/** Shared, non-React signal so any microphone surface can make the field breathe. */
export const ambient = { level: 0 };

const VERTEX = `
attribute vec2 aPos;
void main() { gl_Position = vec4(aPos, 0.0, 1.0); }
`;

// Voice ribbons: a few luminous strands, domain-warped by value noise, that drift slowly,
// lean toward the pointer, and swell with the live microphone level.
const FRAGMENT = `
precision mediump float;
uniform vec2 uRes;
uniform float uTime;
uniform vec2 uPointer;
uniform float uLevel;
uniform vec3 uBg;
uniform vec3 uC1;
uniform vec3 uC2;
uniform vec3 uC3;
uniform float uStrength;

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), u.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), u.x), u.y);
}
float fbm(vec2 p) {
  float v = 0.0;
  float a = 0.5;
  for (int i = 0; i < 4; i++) { v += a * noise(p); p *= 2.03; a *= 0.5; }
  return v;
}

void main() {
  vec2 uv = gl_FragCoord.xy / uRes;
  vec2 p = (gl_FragCoord.xy - 0.5 * uRes) / uRes.y;
  float aspect = uRes.x / uRes.y;
  float t = uTime * 0.05;
  vec2 ptr = vec2((uPointer.x - 0.5) * aspect, (0.5 - uPointer.y));
  vec3 col = uBg;
  float amp = 1.0 + uLevel * 2.2;

  for (int i = 0; i < 5; i++) {
    float fi = float(i);
    float warp = fbm(vec2(p.x * 1.2 + t * (1.0 + fi * 0.2), fi * 3.1 + t));
    float y = 0.16 * sin(p.x * (1.3 + fi * 0.28) + t * (3.0 + fi * 0.7) + fi * 1.9) + 0.22 * (warp - 0.5);
    float lean = exp(-pow(p.x - ptr.x, 2.0) * 3.0) * (ptr.y - 0.25) * 0.28;
    float centre = 0.26 - fi * 0.045;
    float d = abs(p.y - centre - (y + lean) * amp);
    float glow = (0.0028 + uLevel * 0.004) / (d + 0.0035);
    vec3 tint = mix(uC1, uC3, smoothstep(-0.8, 0.8, p.x));
    tint = mix(tint, uC2, 0.5 + 0.5 * sin(fi * 1.7 + t * 4.0));
    col = mix(col, tint, clamp(glow * 0.16 * uStrength, 0.0, 0.85));
  }

  // Fade the field out toward the edges and the lower half, where content lives.
  float fade = smoothstep(1.15, 0.2, length(vec2(p.x * 0.7, (p.y - 0.2) * 1.4)));
  col = mix(uBg, col, fade);
  gl_FragColor = vec4(col, 1.0);
}
`;

function hexToRgb(value: string, fallback: [number, number, number]): [number, number, number] {
  const hex = value.trim().replace('#', '');
  if (!/^[0-9a-f]{6}$/i.test(hex)) return fallback;
  return [0, 2, 4].map(i => parseInt(hex.slice(i, i + 2), 16) / 255) as [number, number, number];
}

function compile(gl: WebGLRenderingContext, type: number, source: string) {
  const shader = gl.createShader(type)!;
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    console.warn('SatyaCheck ambient field: shader failed', gl.getShaderInfoLog(shader));
    return null;
  }
  return shader;
}

/**
 * A fixed, full-viewport WebGL field behind the app. Purely decorative: aria-hidden, no pointer
 * capture, half resolution, paused when hidden, a single still frame under reduced motion, and
 * a quiet CSS fallback when WebGL is unavailable or the context is lost.
 */
export default function AmbientField() {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const node = canvas.current;
    if (!node) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let gl: WebGLRenderingContext | null = null;
    let program: WebGLProgram | null = null;
    let buffer: WebGLBuffer | null = null;
    const shaders: WebGLShader[] = [];
    let frame = 0;
    let running = false;
    const started = performance.now();
    const pointer = { x: 0.62, y: 0.35, tx: 0.62, ty: 0.35 };
    let level = 0;
    let colors = { bg: [0, 0, 0], c1: [0, 0, 0], c2: [0, 0, 0], c3: [0, 0, 0], strength: 1 };
    const uniforms: Record<string, WebGLUniformLocation | null> = {};

    const readColors = () => {
      const style = getComputedStyle(document.documentElement);
      const light = document.documentElement.dataset.theme === 'light';
      colors = {
        bg: hexToRgb(style.getPropertyValue('--bg'), [0.02, 0.02, 0.07]),
        c1: hexToRgb(style.getPropertyValue('--voice-1'), [0.24, 0.34, 1]),
        c2: hexToRgb(style.getPropertyValue('--voice-2'), [0.48, 0.36, 1]),
        c3: hexToRgb(style.getPropertyValue('--voice-3'), [0.22, 0.78, 1]),
        strength: light ? 0.55 : 1,
      };
    };

    const setup = () => {
      gl = node.getContext('webgl', { antialias: false, alpha: false, powerPreference: 'low-power', preserveDrawingBuffer: false });
      if (!gl) { node.dataset.fallback = 'true'; return false; }
      if (gl.isContextLost()) { node.dataset.fallback = 'true'; return false; }
      const vs = compile(gl, gl.VERTEX_SHADER, VERTEX);
      const fs = compile(gl, gl.FRAGMENT_SHADER, FRAGMENT);
      if (!vs || !fs) { node.dataset.fallback = 'true'; return false; }
      shaders.push(vs, fs);
      program = gl.createProgram()!;
      gl.attachShader(program, vs);
      gl.attachShader(program, fs);
      gl.linkProgram(program);
      gl.useProgram(program);
      buffer = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
      const location = gl.getAttribLocation(program, 'aPos');
      gl.enableVertexAttribArray(location);
      gl.vertexAttribPointer(location, 2, gl.FLOAT, false, 0, 0);
      for (const name of ['uRes', 'uTime', 'uPointer', 'uLevel', 'uBg', 'uC1', 'uC2', 'uC3', 'uStrength']) {
        uniforms[name] = gl.getUniformLocation(program, name);
      }
      delete node.dataset.fallback;
      return true;
    };

    const resize = () => {
      // Half resolution: the field is soft by nature, and this keeps it cheap on phones.
      const scale = Math.min(1, (window.devicePixelRatio || 1) * 0.5);
      node.width = Math.max(1, Math.round(window.innerWidth * scale));
      node.height = Math.max(1, Math.round(window.innerHeight * scale));
      gl?.viewport(0, 0, node.width, node.height);
      if (!running) draw(performance.now());
    };

    const draw = (now: number) => {
      if (!gl || !program) return;
      pointer.x += (pointer.tx - pointer.x) * 0.04;
      pointer.y += (pointer.ty - pointer.y) * 0.04;
      level += (ambient.level - level) * 0.12;
      gl.uniform2f(uniforms.uRes, node.width, node.height);
      gl.uniform1f(uniforms.uTime, reduced ? 12 : (now - started) / 1000);
      gl.uniform2f(uniforms.uPointer, pointer.x, pointer.y);
      gl.uniform1f(uniforms.uLevel, level);
      gl.uniform3fv(uniforms.uBg, colors.bg);
      gl.uniform3fv(uniforms.uC1, colors.c1);
      gl.uniform3fv(uniforms.uC2, colors.c2);
      gl.uniform3fv(uniforms.uC3, colors.c3);
      gl.uniform1f(uniforms.uStrength, colors.strength);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    };

    let last = 0;
    const loop = (now: number) => {
      frame = requestAnimationFrame(loop);
      if (now - last < 1000 / 40) return;
      last = now;
      draw(now);
    };
    const start = () => {
      if (running || reduced || document.hidden || !gl) return;
      running = true;
      frame = requestAnimationFrame(loop);
    };
    const stop = () => { running = false; cancelAnimationFrame(frame); };

    readColors();
    if (!setup()) return;
    resize();
    start();

    const onPointer = (event: PointerEvent) => {
      pointer.tx = event.clientX / window.innerWidth;
      pointer.ty = event.clientY / window.innerHeight;
    };
    const onVisibility = () => (document.hidden ? stop() : start());
    const onLost = (event: Event) => { event.preventDefault(); stop(); node.dataset.fallback = 'true'; };
    const onRestored = () => { if (setup()) { resize(); start(); } };
    const themeWatch = new MutationObserver(() => { readColors(); if (!running) draw(performance.now()); });

    window.addEventListener('resize', resize);
    window.addEventListener('pointermove', onPointer, { passive: true });
    document.addEventListener('visibilitychange', onVisibility);
    node.addEventListener('webglcontextlost', onLost);
    node.addEventListener('webglcontextrestored', onRestored);
    themeWatch.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

    return () => {
      stop();
      window.removeEventListener('resize', resize);
      window.removeEventListener('pointermove', onPointer);
      document.removeEventListener('visibilitychange', onVisibility);
      node.removeEventListener('webglcontextlost', onLost);
      node.removeEventListener('webglcontextrestored', onRestored);
      themeWatch.disconnect();
      // Release what this effect created; never kill the context, which a remount reuses.
      if (gl && !gl.isContextLost()) {
        if (buffer) gl.deleteBuffer(buffer);
        if (program) gl.deleteProgram(program);
        shaders.forEach(shader => gl!.deleteShader(shader));
      }
    };
  }, []);

  return <canvas ref={canvas} className="ambient-field" aria-hidden="true" />;
}
