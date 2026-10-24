/* The pipeline machine's geometry: one small station per stage type, pipes between them.
 *
 * World units: x and y on the floor, z up; the camera is the kit's isometric one (azimuth 45°,
 * looking from +x+y, so a station's back is its -x/-y side). Every station stands on a 24×24
 * plinth on one base plate. Parts are listed bottom to top and back to front, which is the
 * order they are painted in. `phase` (0–1, looping) moves the part that shows the stage working,
 * and is 0 when the stage is idle. */

import {
  cylinder, depthOf, dotGrid, iso, lineOnTop, onTop, pathOf, planOutline, radialTicks, sideSeam, slabOf,
  type LineTone, type Point3, type Projection, type SolidPaths, type Tone,
} from "./iso-kit";

export type StageType =
  | "input" | "llm" | "agent" | "tool" | "retriever" | "store" | "router" | "transform"
  | "model" | "train" | "eval" | "queue" | "job" | "output";

export type Drawable =
  | { t: "solid"; p: SolidPaths; tone: Tone; accent?: boolean; halo?: boolean; flat?: boolean }
  | { t: "line"; d: string; tone: LineTone; accent?: boolean; flow?: boolean }
  | { t: "dots"; pts: [number, number][]; tone: Tone; accent?: boolean };

export const PLINTH = 24;
export const BASE_TOP = 3; // the base plate's top
const Z0 = BASE_TOP + 1.6; // top of a plinth: where a station's parts start
export const PIPE = 2.2;

/** What each part looks like, for the legend. */
export const PART_OF: Record<StageType, string> = {
  input: "Hopper", llm: "Engine", agent: "Control tower", tool: "Tool box", retriever: "Disc reader",
  store: "Cabinet", router: "Valve", transform: "Press", model: "Core", train: "Flywheel",
  eval: "Gauge", queue: "Conveyor", job: "Crate", output: "Tray",
};

export const ROLE_OF: Record<StageType, string> = {
  input: "Input", llm: "Model call", agent: "Agent", tool: "Tool", retriever: "Retriever",
  store: "Store", router: "Router", transform: "Transform", model: "ML model", train: "Training",
  eval: "Evaluation", queue: "Queue", job: "Job", output: "Output",
};

const box = (P: Projection, cx: number, cy: number, w: number, d: number, z: number, h: number, r = 1.2, bevel = 0) =>
  slabOf({ x: cx - w / 2, y: cy - d / 2, w, d, r }, z, h, P, 6, bevel);
const can = (P: Projection, cx: number, cy: number, r: number, z: number, h: number) => cylinder(cx, cy, r, z, h, P, 28);
const S = (p: SolidPaths, tone: Tone, extra: Partial<Extract<Drawable, { t: "solid" }>> = {}): Drawable => ({ t: "solid", p, tone, ...extra });
const L = (d: string, tone: LineTone, extra: Partial<Extract<Drawable, { t: "line" }>> = {}): Drawable => ({ t: "line", d, tone, ...extra });
const plan = (cx: number, cy: number, w: number, d: number, r = 1.2) => ({ x: cx - w / 2, y: cy - d / 2, w, d, r });

/** spokes across a disc's top, turned by `angle` */
function spokes(P: Projection, cx: number, cy: number, r: number, z: number, n: number, angle: number) {
  const out: string[] = [];
  for (let i = 0; i < n; i++) {
    const a = angle + (i / n) * Math.PI;
    out.push(lineOnTop([cx - Math.cos(a) * r, cy - Math.sin(a) * r], [cx + Math.cos(a) * r, cy + Math.sin(a) * r], z, P));
  }
  return out.join("");
}

function engine(P: Projection, cx: number, cy: number, phase: number): Drawable[] {
  const parts: Drawable[] = [S(box(P, cx, cy, 18, 18, Z0, 2.4, 2), "mid")];
  let z = Z0 + 2.4;
  for (let k = 0; k < 4; k++) { // body between cooling fins, bottom to top
    parts.push(S(can(P, cx, cy, 6.6, z, 1.8), "hi"));
    parts.push(S(can(P, cx, cy, 8.2, z + 1.8, 0.7), "mid"));
    z += 2.5;
  }
  parts.push(S(can(P, cx, cy, 6.6, z, 1.6), "hi"));
  const lift = phase ? Math.sin(phase * Math.PI * 2) * 0.6 + 0.6 : 0; // the cap breathes while it runs
  parts.push(S(can(P, cx, cy, 4.6, z + 1.6, 2.2 + lift), "hi", { accent: true }));
  parts.push(S(can(P, cx, cy, 1.2, z + 3.8 + lift, 2.4), "mid"));
  return parts;
}

function tower(P: Projection, cx: number, cy: number, phase: number): Drawable[] {
  const top = Z0 + 3 + 9 + 7;
  const blink = phase ? (Math.sin(phase * Math.PI * 4) > 0 ? 1 : 0) : 1;
  return [
    S(box(P, cx, cy, 16, 16, Z0, 3, 2), "mid"),
    S(can(P, cx, cy, 4.2, Z0 + 3, 9), "hi"),
    S(box(P, cx, cy, 13, 13, Z0 + 12, 7, 2, 0.8), "hi", { accent: true }),
    L(sideSeam(plan(cx, cy, 13, 13, 2), Z0 + 15.5, P), "mid"),
    S(can(P, cx + 3, cy - 3, 0.5, top, 4), "mid"),
    S(can(P, cx + 3, cy - 3, 1.2, top + 4, 1.2), blink ? "hi" : "lo", { accent: !!blink }),
  ];
}

function toolbox(P: Projection, cx: number, cy: number, phase: number): Drawable[] {
  const p = plan(cx, cy, 18, 13, 1.4);
  const knob = phase ? Math.sin(phase * Math.PI * 2) : 0;
  return [
    S(box(P, cx, cy, 18, 13, Z0, 9, 1.4, 0.6), "hi"),
    L(sideSeam(p, Z0 + 3, P), "faint"),
    L(sideSeam(p, Z0 + 6, P), "faint"),
    S(box(P, cx - 4.5, cy, 3, 6, Z0 + 9, 1.2, 0.6), "mid"),
    S(box(P, cx - 4.5, cy + 1.2 * knob, 1.4, 2, Z0 + 10.2, 2.2, 0.4), "mid"),
    S(can(P, cx + 4, cy, 3, Z0 + 9, 1.2), "mid"),
    S(can(P, cx + 4, cy, 2, Z0 + 10.2, 2.6), "hi", { accent: true }),
    L(spokes(P, cx + 4, cy, 2, Z0 + 12.8, 1, knob * 1.2), "lo"),
  ];
}

function discs(P: Projection, cx: number, cy: number, phase: number): Drawable[] {
  const parts: Drawable[] = [S(box(P, cx, cy, 18, 18, Z0, 2.2, 2), "mid")];
  let z = Z0 + 2.2;
  for (let k = 0; k < 4; k++) {
    parts.push(S(can(P, cx, cy, 1.4, z, 1), "mid"));
    parts.push(S(can(P, cx, cy, 8.4, z + 1, 1.5), "hi", { accent: k === 3 }));
    z += 2.5;
  }
  parts.push(S(can(P, cx, cy, 1.6, z, 1.4), "mid"));
  // the read arm swings over the top platter
  const a = -Math.PI / 4 + (phase ? Math.sin(phase * Math.PI * 2) * 0.35 : 0);
  const px = cx - 8, py = cy + 8;
  parts.push(S(can(P, px, py, 1.6, Z0 + 2.2, z - Z0 - 0.4), "mid"));
  parts.push(L(onTop([[px, py], [px + Math.cos(a) * 9, py + Math.sin(a) * 9]], z + 0.4, P), "hi"));
  return parts;
}

function cabinet(P: Projection, cx: number, cy: number, phase: number): Drawable[] {
  const p = plan(cx, cy, 18, 15, 1);
  const out = phase ? Math.sin(phase * Math.PI) * 4 : 0; // the middle drawer slides out
  const parts: Drawable[] = [
    S(box(P, cx, cy, 18, 15, Z0, 18, 1, 0.6), "hi"),
    L(sideSeam(p, Z0 + 6, P), "lo"),
    L(sideSeam(p, Z0 + 12, P), "lo"),
  ];
  if (out) parts.push(S(box(P, cx + out / 2, cy + 0.4, 18 - 1.6 + out, 13.4, Z0 + 6.6, 4.8, 0.6), "hi", { accent: true }));
  parts.push(S(box(P, cx, cy, 9, 5, Z0 + 18, 0.6, 0.4), "mid", { accent: !out }));
  parts.push(L(lineOnTop([cx - 3, cy - 0.8], [cx + 3, cy - 0.8], Z0 + 18.6, P) + lineOnTop([cx - 3, cy + 0.8], [cx + 1, cy + 0.8], Z0 + 18.6, P), "lo"));
  return parts;
}

function valve(P: Projection, cx: number, cy: number, phase: number): Drawable[] {
  const wheel = Z0 + 2 + 7 + 3 + 3.5;
  return [
    S(box(P, cx, cy, 16, 16, Z0, 2, 2), "mid"),
    S(box(P, cx, cy, 20, 5, Z0 + 2, 5, 2.4), "mid"), // the pipe body runs through it
    S(can(P, cx, cy, 6, Z0 + 2, 7), "hi"),
    S(can(P, cx, cy, 3.6, Z0 + 9, 3), "mid"),
    S(can(P, cx, cy, 1, Z0 + 12, 3.5), "mid"),
    S(can(P, cx, cy, 7.4, wheel, 1.1), "hi", { accent: true }),
    L(spokes(P, cx, cy, 6.6, wheel + 1.1, 3, phase * Math.PI * 2), "lo"),
    S(can(P, cx, cy, 1.6, wheel + 1.1, 0.8), "mid"),
  ];
}

function hopper(P: Projection, cx: number, cy: number, phase: number): Drawable[] {
  const parts: Drawable[] = [S(box(P, cx, cy, 12, 12, Z0, 1.6, 1), "mid")];
  for (const [dx, dy] of [[-5, -5], [5, -5], [-5, 5], [5, 5]]) parts.push(S(can(P, cx + dx, cy + dy, 0.9, Z0 + 1.6, 7), "mid"));
  parts.push(S(can(P, cx, cy, 2.6, Z0 + 1.6, 7), "mid"));
  const top = Z0 + 8.6 + 7;
  parts.push(S(box(P, cx, cy, 20, 20, Z0 + 8.6, 7, 1.6, 0.6), "hi", { accent: true }));
  parts.push(L(planOutline(plan(cx, cy, 16, 16, 1), top, P), "lo"));
  parts.push(L(planOutline(plan(cx, cy, 9, 9, 0.6), top, P), "faint"));
  if (phase) parts.push({ t: "dots", pts: dotGrid(cx - 4, cy - 4, 3, 3, 4, top, P).map(([x, y]) => [x, y + Math.sin(phase * Math.PI * 2) * 0.8]), tone: "hi" });
  return parts;
}

function tray(P: Projection, cx: number, cy: number, phase: number): Drawable[] {
  const parts: Drawable[] = [
    S(box(P, cx, cy - 8, 20, 2, Z0, 8, 0.6), "mid"), // back stop
    S(box(P, cx, cy + 1, 20, 15, Z0, 2.6, 1.4), "mid"),
  ];
  const sheets = 3 + (phase > 0.5 ? 1 : 0);
  for (let k = 0; k < sheets; k++) parts.push(S(box(P, cx, cy + 1.5, 15, 11, Z0 + 2.6 + k * 0.9, 0.9, 0.3), "hi", { accent: k === sheets - 1 }));
  const z = Z0 + 2.6 + sheets * 0.9;
  parts.push(L(lineOnTop([cx - 5, cy - 1], [cx + 4, cy - 1], z, P) + lineOnTop([cx - 5, cy + 1.5], [cx + 5, cy + 1.5], z, P) + lineOnTop([cx - 5, cy + 4], [cx + 1, cy + 4], z, P), "faint"));
  return parts;
}

function press(P: Projection, cx: number, cy: number, phase: number): Drawable[] {
  const head = Z0 + 3 + 14;
  const ram = phase ? 0.5 - 0.5 * Math.cos(phase * Math.PI * 2) : 0; // presses down and back up
  const ramBottom = Z0 + 9 - ram * 3.4;
  return [
    S(box(P, cx, cy, 20, 14, Z0, 3, 1.4), "mid"),
    S(can(P, cx - 7, cy - 4.5, 1.1, Z0 + 3, 14), "mid"),
    S(can(P, cx + 7, cy - 4.5, 1.1, Z0 + 3, 14), "mid"),
    S(box(P, cx, cy, 8, 8, Z0 + 3, 2.2, 0.6), "lo"),
    S(can(P, cx, cy, 3.2, ramBottom, head - ramBottom), "hi", { accent: true }),
    S(can(P, cx - 7, cy + 4.5, 1.1, Z0 + 3, 14), "mid"),
    S(can(P, cx + 7, cy + 4.5, 1.1, Z0 + 3, 14), "mid"),
    S(box(P, cx, cy, 20, 14, head, 3, 1.4, 0.6), "hi"),
  ];
}

function core(P: Projection, cx: number, cy: number, phase: number): Drawable[] {
  const glow = phase ? (Math.sin(phase * Math.PI * 2) > 0 ? "hi" : "mid") : "mid";
  return [
    S(box(P, cx, cy, 18, 18, Z0, 2.4, 2), "mid"),
    S(box(P, cx, cy, 13, 13, Z0 + 2.4, 13, 1, 0.8), "hi"),
    L(sideSeam(plan(cx, cy, 13, 13, 1), Z0 + 6.8, P) + sideSeam(plan(cx, cy, 13, 13, 1), Z0 + 11.2, P), "faint"),
    S(box(P, cx, cy, 8, 8, Z0 + 15.4, 1.2, 0.6), "hi", { accent: true }),
    { t: "dots", pts: dotGrid(cx - 2.5, cy - 2.5, 3, 3, 2.5, Z0 + 16.6, P), tone: glow as Tone },
  ];
}

function flywheel(P: Projection, cx: number, cy: number, phase: number): Drawable[] {
  return [
    S(box(P, cx - 7, cy - 6, 8, 8, Z0, 7, 1), "mid"), // motor at the back
    S(box(P, cx + 1, cy + 1, 18, 18, Z0, 2.2, 2), "mid"),
    S(can(P, cx + 1, cy + 1, 9.6, Z0 + 2.2, 2.4), "hi"),
    L(spokes(P, cx + 1, cy + 1, 9, Z0 + 4.6, 3, phase * Math.PI * 4), "lo"),
    L(planOutline(plan(cx + 1, cy + 1, 14, 14, 7), Z0 + 4.6, P), "faint"),
    S(can(P, cx + 1, cy + 1, 2.4, Z0 + 4.6, 2.2), "hi", { accent: true }),
  ];
}

function gauge(P: Projection, cx: number, cy: number, phase: number): Drawable[] {
  const z = Z0 + 2 + 10 + 1.8;
  const ticks = radialTicks(cx, cy, 7.4, 12, 3, z, [1, 2], P, -Math.PI * 0.75, Math.PI * 1.5);
  const a = -Math.PI * 0.75 + Math.PI * 1.5 * (phase ? 0.2 + 0.7 * (0.5 - 0.5 * Math.cos(phase * Math.PI * 2)) : 0.62);
  return [
    S(box(P, cx, cy, 11, 11, Z0, 2, 1.2), "mid"),
    S(can(P, cx, cy, 1.6, Z0 + 2, 10), "mid"),
    S(can(P, cx, cy, 8.4, Z0 + 12, 1.8), "hi", { accent: true }),
    L(ticks.minor, "lo"),
    L(ticks.major, "mid"),
    L(lineOnTop([cx, cy], [cx + Math.sin(a) * 6, cy - Math.cos(a) * 6], z, P), "hi"),
    S(can(P, cx, cy, 0.9, z, 0.5), "mid"),
  ];
}

function conveyor(P: Projection, cx: number, cy: number, phase: number): Drawable[] {
  const parts: Drawable[] = [
    S(box(P, cx, cy, 22, 9, Z0, 4, 1.2), "mid"),
  ];
  const top = Z0 + 4;
  let rollers = "";
  for (let x = -9; x <= 9; x += 3) rollers += lineOnTop([cx + x, cy - 4], [cx + x, cy + 4], top, P);
  parts.push(L(rollers, "faint"));
  const shift = phase * 6;
  for (const [k, x0] of [-7, -1, 5].entries()) {
    const x = ((x0 + shift + 9) % 18) - 9;
    parts.push(S(box(P, cx + x, cy, 3.6, 4.2, top, 3, 0.4), "hi", { accent: k === 2 }));
  }
  return parts;
}

function crate(P: Projection, cx: number, cy: number, phase: number): Drawable[] {
  const p = plan(cx, cy, 17, 17, 0.8);
  const lid = phase ? Math.sin(phase * Math.PI) * 2 : 0;
  return [
    S(box(P, cx, cy, 17, 17, Z0, 11, 0.8, 0.5), "hi"),
    L(sideSeam(p, Z0 + 3.7, P) + sideSeam(p, Z0 + 7.4, P), "faint"),
    S(box(P, cx, cy, 18, 18, Z0 + 11 + lid, 1.4, 1, 0.4), "mid"),
    S(box(P, cx, cy, 8, 4, Z0 + 12.4 + lid, 0.5, 0.4), "hi", { accent: true }),
  ];
}

const BUILD: Record<StageType, (P: Projection, cx: number, cy: number, phase: number) => Drawable[]> = {
  input: hopper, llm: engine, agent: tower, tool: toolbox, retriever: discs, store: cabinet, router: valve,
  transform: press, model: core, train: flywheel, eval: gauge, queue: conveyor, job: crate, output: tray,
};

/** One station: its plinth and its machine part. */
export function station(type: StageType, P: Projection, cx: number, cy: number, phase: number): Drawable[] {
  const h = PLINTH / 2;
  return [
    S(slabOf(plan(cx, cy, PLINTH, PLINTH, 2), BASE_TOP, 1.6, P, 6, 0.4), "lo", { halo: true }),
    ...(BUILD[type] ?? press)(P, cx, cy, phase),
    L(onTop([[cx - h + 2, cy + h - 0.01], [cx + h - 2, cy + h - 0.01]], BASE_TOP + 0.8, P), "faint"),
  ];
}

export function basePlate(P: Projection, x0: number, y0: number, x1: number, y1: number): Drawable[] {
  return [S(slabOf({ x: x0, y: y0, w: x1 - x0, d: y1 - y0, r: 4 }, 0, BASE_TOP, P, 8, 0.6), "lo", { halo: true })];
}

export type PipeRun = { depth: number; solid: SolidPaths; flow: string };

/** A pipe along a route on the base plate: one solid per straight run, each with its flow line on
 *  top, so a run hidden behind a station is painted (and covered) like any other part. */
export function pipe(P: Projection, route: [number, number][]): PipeRun[] {
  const runs: PipeRun[] = [];
  const r = PIPE / 2;
  for (let i = 0; i < route.length - 1; i++) {
    const [ax, ay] = route[i];
    const [bx, by] = route[i + 1];
    if (Math.hypot(bx - ax, by - ay) < 0.01) continue;
    const x = Math.min(ax, bx) - r, y = Math.min(ay, by) - r;
    const w = Math.abs(bx - ax) + PIPE, d = Math.abs(by - ay) + PIPE;
    runs.push({
      depth: depthOf([(ax + bx) / 2, (ay + by) / 2, BASE_TOP], P),
      solid: slabOf({ x, y, w, d, r: 0.6 }, BASE_TOP, PIPE, P, 3),
      flow: pathOf([iso([ax, ay, BASE_TOP + PIPE], P), iso([bx, by, BASE_TOP + PIPE], P)]),
    });
  }
  return runs;
}

export const depthAt = (P: Projection, x: number, y: number) => depthOf([x, y, Z0] as Point3, P);
