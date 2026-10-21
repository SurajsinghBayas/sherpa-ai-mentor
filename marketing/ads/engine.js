// Tiny deterministic animation engine for the ads. Every frame is a pure function of time t (seconds),
// so render.mjs can step through frames exactly; opening the page in a browser plays it in real time.

const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
/** 0→1 progress of t through [a, b] */
const p = (t, a, b) => clamp((t - a) / (b - a));
const easeOut = (x) => 1 - Math.pow(1 - x, 3);
const easeInOut = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
/** opacity for something shown during [a, b], fading over `f` seconds at each end */
const vis = (t, a, b, f = 0.35) => Math.min(p(t, a, a + f), 1 - p(t, b - f, b));
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

/** Set opacity + a rise-in transform: enters from `dy` px below over `d` seconds starting at `a`. */
function rise(el, t, a, b, { dy = 40, d = 0.6, scale = 1 } = {}) {
  if (typeof el === "string") el = $(el);
  const k = easeOut(p(t, a, a + d));
  el.style.opacity = vis(t, a, b);
  el.style.transform = `translateY(${(1 - k) * dy}px) scale(${scale + (1 - scale) * k})`;
}

/** Typewriter: the first n characters of `text` by progress through [a, b]. */
const typed = (text, t, a, b) => text.slice(0, Math.round(text.length * p(t, a, b)));

/** Subtitles: [{a, b, text}] → the bottom caption band (ads are mostly watched muted). */
function captions(t, lines) {
  const el = $("#caption");
  const cur = lines.find((l) => t >= l.a && t < l.b);
  el.textContent = cur ? cur.text : "";
  el.style.opacity = cur ? vis(t, cur.a, cur.b, 0.2) : 0;
}

/** Play in real time when opened directly; render.mjs calls window.render(t) itself. */
function boot(render, duration) {
  window.render = render;
  window.DURATION = duration;
  window.ready = document.fonts.ready.then(() => render(0));
  if (!new URLSearchParams(location.search).has("still")) {
    window.ready.then(() => {
      const start = performance.now();
      const tick = () => {
        const t = ((performance.now() - start) / 1000) % duration;
        render(t);
        if (!window.__frozen) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
  }
}
