"use client";

/* Repo City: every file a building, every component a district, drawn with Anatomy's isometric kit.
 *
 * Height is the file's line count (log scale), footprint its number of definitions; docs and config
 * files are the low-rise district. Heat (paper → Sherpa blue) shows how often a file changed or
 * how recently. Picking a building lights the files it imports (solid arcs) and the files that
 * import it (dashed arcs), and dims the rest: what a change there could touch.
 *
 * The time-lapse replays the commit history: buildings appear when their file was added, grow
 * with every commit that touches them, and glow in the frame they change. */

import { memo, useEffect, useMemo, useRef, useState, type PointerEvent as RPointerEvent, type WheelEvent } from "react";
import type { City as CityData, CityBuilding } from "../../lib/api";
import { Draw } from "./draw";
import { depthOf, fitProjection, iso, sideSeam, slabOf, type Projection } from "./iso-kit";

export type HeatMode = "changes" | "recent" | "none";

const CELL = 11;
const PAD = 4;
const STREET = 9;
const W = 1000;
const GROUND = 3.2; // top of a district's plinth
const FLOOR = 4; // a floor line every this many units up a tall building
const PLAY_MS = 22000; // a whole time-lapse takes about this long
const CHAR = 0.66; // a monospace label's advance per character, as a share of its font size

/** the district name cut to fit its block's front edge, so neighbouring labels never run together */
function fitLabel(name: string, room: number, size: number) {
  const n = Math.floor(room / (size * CHAR));
  if (name.length <= n) return name;
  return n >= 4 ? name.slice(0, n - 1).trimEnd() + "…" : "";
}

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));
const sideOf = (b: CityBuilding, code: boolean) => (code ? clamp(4 + Math.sqrt(b.defs) * 1.3, 4, 9) : 4.4);
const heightOf = (b: CityBuilding, code: boolean) =>
  code ? 2.5 + 6.5 * Math.log2(1 + b.lines / 25) : clamp(1.2 + 1.6 * Math.log2(1 + b.lines / 40), 1.2, 7);

type Lot = { i: number; cx: number; cy: number; side: number; h: number; code: boolean; depth: number };
type Block = { d: number; x: number; y: number; w: number; dd: number };

function layout(city: CityData) {
  const members: number[][] = city.districts.map(() => []);
  city.buildings.forEach((b, i) => members[b.district]?.push(i));
  const blocks = city.districts
    .map((_, d) => {
      const n = members[d].length;
      const cols = Math.max(1, Math.ceil(Math.sqrt(n)));
      const rows = Math.max(1, Math.ceil(n / cols));
      return { d, cols, w: cols * CELL + PAD * 2, dd: rows * CELL + PAD * 2 };
    })
    .filter((b) => members[b.d].length)
    .sort((a, b) => b.w * b.dd - a.w * a.dd);
  // shelf packing: rows of blocks, about as wide as the whole city is deep
  const area = blocks.reduce((s, b) => s + (b.w + STREET) * (b.dd + STREET), 0);
  const target = Math.max(Math.sqrt(area) * 1.15, ...blocks.map((b) => b.w));
  const placed: Block[] = [];
  let x = 0, y = 0, shelf = 0;
  for (const b of blocks) {
    if (x > 0 && x + b.w > target) {
      x = 0;
      y += shelf + STREET;
      shelf = 0;
    }
    placed.push({ d: b.d, x, y, w: b.w, dd: b.dd });
    x += b.w + STREET;
    shelf = Math.max(shelf, b.dd);
  }
  const lots: Lot[] = [];
  for (const blk of placed) {
    const cols = blocks.find((b) => b.d === blk.d)!.cols;
    const code = city.districts[blk.d].code;
    members[blk.d].forEach((i, k) => {
      const b = city.buildings[i];
      const cx = blk.x + PAD + (k % cols) * CELL + CELL / 2;
      const cy = blk.y + PAD + Math.floor(k / cols) * CELL + CELL / 2;
      lots.push({ i, cx, cy, side: sideOf(b, code), h: heightOf(b, code), code, depth: 0 });
    });
  }
  const x1 = Math.max(...placed.map((b) => b.x + b.w)), y1 = Math.max(...placed.map((b) => b.y + b.dd));
  return { blocks: placed, lots, bounds: { x0: -8, y0: -8, x1: x1 + 8, y1: y1 + 8 } };
}

function fit(bounds: { x0: number; x1: number; y0: number; y1: number }, tallest: number) {
  const { x0, x1, y0, y1 } = bounds;
  const pts: [number, number, number][] = [];
  for (const x of [x0, x1]) for (const y of [y0, y1]) for (const z of [0, tallest + GROUND]) pts.push([x, y, z]);
  const unit = pts.map((p) => iso(p, { origin: [0, 0], scale: 1 }));
  const w = Math.max(...unit.map((p) => p[0])) - Math.min(...unit.map((p) => p[0]));
  const h = Math.max(...unit.map((p) => p[1])) - Math.min(...unit.map((p) => p[1]));
  const H = Math.round(clamp((W * h) / w + 20, 340, 760));
  return { P: fitProjection(pts, W, H, { pad: 34 }), H };
}

/** heat 0–3 by how often each file changed (top 10% → 3) or how recently (≤30 days of the newest change → 3) */
function heats(city: CityData, mode: HeatMode): number[] {
  if (mode === "none") return city.buildings.map(() => 0);
  if (mode === "changes") {
    const sorted = city.buildings.map((b) => b.changes).filter((c) => c > 0).sort((a, b) => b - a);
    const cut = (q: number) => sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * q))] ?? Infinity;
    const [c3, c2] = [cut(0.1), cut(0.35)];
    return city.buildings.map((b) => (b.changes <= 0 ? 0 : b.changes >= c3 ? 3 : b.changes >= c2 ? 2 : 1));
  }
  const newest = Math.max(0, ...city.buildings.map((b) => b.last ?? 0));
  const day = 86400;
  return city.buildings.map((b) =>
    !b.last ? 0 : newest - b.last <= 30 * day ? 3 : newest - b.last <= 120 * day ? 2 : newest - b.last <= 400 * day ? 1 : 0,
  );
}

const Building = memo(function Building({
  lot, P, h, heat, lit, dim, onPick, onHover,
}: {
  lot: Lot; P: Projection; h: number; heat: number; lit: boolean; dim: boolean;
  onPick: (i: number) => void; onHover: (i: number | null, e?: RPointerEvent) => void;
}) {
  const parts = useMemo(() => {
    const plan = { x: lot.cx - lot.side / 2, y: lot.cy - lot.side / 2, w: lot.side, d: lot.side, r: 0.5 };
    const body = slabOf(plan, GROUND, h, P, 2);
    let floors = "";
    if (lot.code) for (let z = GROUND + FLOOR; z < GROUND + h - 1.5; z += FLOOR) floors += sideSeam(plan, z, P);
    return { body, floors };
  }, [lot, P, h]);
  if (h <= 0.05) return null;
  return (
    <g
      className="cb"
      data-heat={heat || undefined}
      data-dim={dim || undefined}
      data-doc={!lot.code || undefined}
      onPointerEnter={(e) => onHover(lot.i, e)}
      onPointerMove={(e) => onHover(lot.i, e)}
      onPointerLeave={() => onHover(null)}
      onClick={() => onPick(lot.i)}
    >
      <Draw d={{ t: "solid", p: parts.body, tone: lot.code ? "hi" : "mid", accent: true }} lit={lit} />
      {parts.floors && <path className="iso-line" data-tone="faint" d={parts.floors} />}
    </g>
  );
});

export function CityView({
  city, heat, selected, onSelect, frame, onHover,
}: {
  city: CityData;
  heat: HeatMode;
  selected: number | null;
  onSelect: (i: number | null) => void;
  /** null shows today; a number shows the city as of that timeline frame */
  frame: number | null;
  onHover: (i: number | null, at?: { x: number; y: number }) => void;
}) {
  const { blocks, lots, bounds } = useMemo(() => layout(city), [city]);
  const tallest = useMemo(() => Math.max(10, ...lots.map((l) => l.h)), [lots]);
  const { P, H } = useMemo(() => fit(bounds, tallest), [bounds, tallest]);
  const ordered = useMemo(
    () => lots.map((l) => ({ ...l, depth: depthOf([l.cx, l.cy, 0], P) })).sort((a, b) => a.depth - b.depth),
    [lots, P],
  );
  const byIndex = useMemo(() => Object.fromEntries(lots.map((l) => [l.i, l])) as Record<number, Lot>, [lots]);
  const staticHeat = useMemo(() => heats(city, heat), [city, heat]);
  // every frame each building changed in, for growth and glow during the time-lapse
  const touches = useMemo(() => {
    const t: number[][] = city.buildings.map(() => []);
    city.timeline.forEach((f, n) => f.changed.forEach((i) => t[i]?.push(n)));
    return t;
  }, [city]);

  // blast radius: what the picked file imports, and what imports it
  const { uses, usedBy } = useMemo(() => {
    const uses = new Set<number>(), usedBy = new Set<number>();
    if (selected != null) for (const [a, b] of city.edges) {
      if (a === selected) uses.add(b);
      if (b === selected) usedBy.add(a);
    }
    return { uses, usedBy };
  }, [city, selected]);

  const stateOf = (i: number) => {
    const b = city.buildings[i];
    const l = byIndex[i];
    if (frame == null) return { h: l.h, heat: staticHeat[i], lit: selected === i };
    if (b.born > frame) return { h: 0, heat: 0, lit: false };
    const ts = touches[i];
    let k = 0;
    while (k < ts.length && ts[k] <= frame) k++;
    const grown = ts.length ? 0.35 + (0.65 * k) / ts.length : 1;
    const since = k ? frame - ts[k - 1] : Infinity;
    return {
      h: Math.round(l.h * grown * 10) / 10,
      heat: since === 0 ? 3 : since <= 3 ? 2 : since <= 10 ? 1 : 0,
      lit: since === 0 || selected === i,
    };
  };

  // zoom and pan
  const svgRef = useRef<SVGSVGElement>(null);
  const [view, setView] = useState({ k: 1, x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const toSvg = (cx: number, cy: number) => {
    const m = svgRef.current?.getScreenCTM();
    if (!m) return { x: 0, y: 0 };
    const p = new DOMPoint(cx, cy).matrixTransform(m.inverse());
    return { x: p.x, y: p.y };
  };
  const zoomAt = (factor: number, at: { x: number; y: number }) =>
    setView((v) => {
      const k = clamp(v.k * factor, 1, 6);
      const f = k / v.k;
      return k === 1 ? { k: 1, x: 0, y: 0 } : { k, x: at.x - (at.x - v.x) * f, y: at.y - (at.y - v.y) * f };
    });
  useEffect(() => setView({ k: 1, x: 0, y: 0 }), [city]);
  const [narrow, setNarrow] = useState(false); // phones draw labels larger (see .city-district)
  useEffect(() => {
    const mq = window.matchMedia?.("(max-width: 560px)");
    if (!mq) return;
    const on = () => setNarrow(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  const onWheel = (e: WheelEvent) => {
    if (!e.ctrlKey && !e.metaKey && view.k === 1 && Math.abs(e.deltaY) < 40) return; // let the page scroll
    e.preventDefault();
    zoomAt(e.deltaY < 0 ? 1.18 : 1 / 1.18, toSvg(e.clientX, e.clientY));
  };
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const stop = (e: Event) => (e as globalThis.WheelEvent).ctrlKey && e.preventDefault(); // no browser zoom
    el.addEventListener("wheel", stop, { passive: false });
    return () => el.removeEventListener("wheel", stop);
  }, []);

  const pick = (i: number) => {
    if (drag.current?.moved) return;
    onSelect(selected === i ? null : i);
  };
  const hover = (i: number | null, e?: RPointerEvent) => {
    if (drag.current) return;
    onHover(i, e ? { x: e.clientX, y: e.clientY } : undefined);
  };

  const top = (i: number) => {
    const l = byIndex[i];
    return iso([l.cx, l.cy, GROUND + stateOf(i).h], P);
  };
  const arc = (a: number, b: number) => {
    const [x1, y1] = top(a), [x2, y2] = top(b);
    const lift = Math.min(90, 18 + Math.hypot(x2 - x1, y2 - y1) * 0.35);
    return `M${x1} ${y1}Q${(x1 + x2) / 2} ${Math.min(y1, y2) - lift} ${x2} ${y2}`;
  };
  const base = useMemo(
    () => slabOf({ x: bounds.x0, y: bounds.y0, w: bounds.x1 - bounds.x0, d: bounds.y1 - bounds.y0, r: 4 }, 0, 2, P, 8, 0.6),
    [bounds, P],
  );
  const plinths = useMemo(
    () => blocks.map((b) => ({ b, p: slabOf({ x: b.x, y: b.y, w: b.w, d: b.dd, r: 2 }, 2, GROUND - 2, P, 6) })),
    [blocks, P],
  );

  return (
    <svg
      ref={svgRef}
      className="iso-svg city-svg"
      data-zoomed={view.k > 1 || undefined}
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={`${city.buildings.length} files in ${city.districts.length} districts`}
      onWheel={onWheel}
      onPointerDown={(e) => {
        if (view.k > 1) drag.current = { x: e.clientX, y: e.clientY, moved: false };
      }}
      onPointerMove={(e) => {
        const d = drag.current;
        if (!d) return;
        const a = toSvg(d.x, d.y), b = toSvg(e.clientX, e.clientY);
        if (Math.hypot(e.clientX - d.x, e.clientY - d.y) > 3) d.moved = true;
        if (d.moved) {
          setView((v) => ({ ...v, x: v.x + (b.x - a.x), y: v.y + (b.y - a.y) }));
          d.x = e.clientX;
          d.y = e.clientY;
        }
      }}
      onPointerUp={() => setTimeout(() => (drag.current = null), 0)}
      onPointerLeave={() => (drag.current = null)}
      onDoubleClick={(e) => zoomAt(view.k > 1 ? 0 : 2, toSvg(e.clientX, e.clientY))}
    >
      <g transform={`translate(${view.x} ${view.y}) scale(${view.k})`}>
        <Draw d={{ t: "solid", p: base, tone: "lo", halo: true }} lit={false} />
        {plinths.map(({ b, p }) => (
          <g key={b.d} onClick={() => !drag.current?.moved && onSelect(null)}>
            <Draw d={{ t: "solid", p, tone: "lo" }} lit={false} />
          </g>
        ))}
        {ordered.map((l) => {
          const st = stateOf(l.i);
          const related = selected == null || l.i === selected || uses.has(l.i) || usedBy.has(l.i);
          return (
            <Building key={l.i} lot={l} P={P} h={st.h} heat={st.heat} lit={st.lit} dim={!related}
              onPick={pick} onHover={hover} />
          );
        })}
        {selected != null && (
          <g className="city-arcs" pointerEvents="none">
            {[...usedBy].map((i) => <path key={`b${i}`} className="iso-line" data-tone="lit" data-dashed="" d={arc(i, selected)} />)}
            {[...uses].map((i) => <path key={`u${i}`} className="iso-line" data-tone="lit" d={arc(selected, i)} />)}
          </g>
        )}
        {plinths.map(({ b }) => {
          const [x, y] = iso([b.x, b.y + b.dd + 2.5, 2], P);
          const [x2, y2] = iso([b.x + b.w + STREET - 2, b.y + b.dd + 2.5, 2], P);
          const name = city.districts[b.d].name;
          const label = fitLabel(name, Math.hypot(x2 - x, y2 - y), narrow ? 18 : 11);
          if (!label) return null;
          return (
            <text key={b.d} className="mc-label city-district" x={x} y={y + 10} textAnchor="start" transform={`rotate(26.6 ${x} ${y + 10})`}>
              {label !== name && <title>{name}</title>}
              {label}
            </text>
          );
        })}
      </g>
    </svg>
  );
}

export { PLAY_MS };
