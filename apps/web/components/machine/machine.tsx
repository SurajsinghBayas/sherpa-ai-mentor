"use client";

/* The pipeline drawn as one small machine: a station per stage on a shared base plate, pipes for
 * the hand-offs, return pipes (along the back) for loops, and long hops along the front.
 * Click a station to read about it; "Run" lights each stage and pipe in execution order and sets
 * that station's part moving. */

import { memo, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { fitProjection, iso, type Projection } from "./iso-kit";
import * as voice from "../../lib/voice";
import { Draw } from "./draw";
import {
  basePlate, depthAt, pipe, PLINTH, ROLE_OF, station, BASE_TOP,
  type PipeRun, type StageType,
} from "./machine-parts";

export type MachineStage = { id: string; name: string; type: StageType };
export type MachineLink = { from: string; to: string; label: string; loop: boolean };

const GAP_X = 46;
const GAP_Y = 52; // room for a label between rows
const LANE = 21; // how far outside the stations the back and front lanes run
const W = 1000;
const STAGE_MS = 1300;
const LINK_MS = 700;

type Placed = MachineStage & { n: number; cx: number; cy: number };
type Routed = MachineLink & { runs: PipeRun[] };
type Step = { kind: "stage"; id: string } | { kind: "link"; at: number };

function layout(stages: MachineStage[], links: MachineLink[]) {
  // columns: longest path over forward links, so every hand-off runs left to right
  const layer: Record<string, number> = Object.fromEntries(stages.map((s) => [s.id, 0]));
  for (let pass = 0; pass < stages.length; pass++)
    for (const l of links) if (!l.loop && layer[l.to] < layer[l.from] + 1) layer[l.to] = layer[l.from] + 1;
  const columns: Record<number, MachineStage[]> = {};
  stages.forEach((s) => (columns[layer[s.id]] ??= []).push(s));
  const placed: Placed[] = stages.map((s, n) => {
    const col = columns[layer[s.id]];
    const i = col.indexOf(s);
    return { ...s, n: n + 1, cx: layer[s.id] * GAP_X, cy: (i - (col.length - 1) / 2) * GAP_Y };
  });
  const at = Object.fromEntries(placed.map((p) => [p.id, p]));
  const h = PLINTH / 2;
  const ys = placed.map((p) => p.cy);
  const back = Math.min(...ys) - h - LANE;
  const front = Math.max(...ys) + h + LANE;
  // spread several pipes leaving (or entering) the same side so they don't overlap
  const sides: Record<string, number> = {};
  const slot = (key: string) => (sides[key] = (sides[key] ?? -1) + 1);
  let backLanes = 0, frontLanes = 0;
  const routes: [number, number][][] = links.map((l) => {
    const a = at[l.from], b = at[l.to];
    if (l.loop) {
      const lane = back - backLanes++ * 4.5;
      const ox = slot(`${a.id}:back`) * 4 - 3, ix = slot(`${b.id}:back`) * 4 + 3;
      return [[a.cx + ox, a.cy - h], [a.cx + ox, lane], [b.cx + ix, lane], [b.cx + ix, b.cy - h]];
    }
    if (layer[b.id] - layer[a.id] > 1) {
      const lane = front + frontLanes++ * 4.5;
      const ox = slot(`${a.id}:front`) * 4 + 3, ix = slot(`${b.id}:front`) * 4 - 3;
      return [[a.cx + ox, a.cy + h], [a.cx + ox, lane], [b.cx + ix, lane], [b.cx + ix, b.cy + h]];
    }
    const oy = slot(`${a.id}:out`) * 4, iy = slot(`${b.id}:in`) * 4;
    const ay = a.cy + oy, by = b.cy + iy;
    const mid = (a.cx + h + b.cx - h) / 2;
    return ay === by ? [[a.cx + h, ay], [b.cx - h, by]] : [[a.cx + h, ay], [mid, ay], [mid, by], [b.cx - h, by]];
  });
  const xs = placed.map((p) => p.cx);
  const bounds = {
    x0: Math.min(...xs) - h - 8, x1: Math.max(...xs) + h + 8,
    y0: (backLanes ? back - (backLanes - 1) * 4.5 : Math.min(...ys) - h) - 8,
    y1: (frontLanes ? front + (frontLanes - 1) * 4.5 : Math.max(...ys) + h) + 8,
  };
  return { placed, routes, bounds };
}

function fit(bounds: { x0: number; x1: number; y0: number; y1: number }): { P: Projection; H: number } {
  const { x0, x1, y0, y1 } = bounds;
  const corners: [number, number, number][] = [];
  for (const x of [x0, x1]) for (const y of [y0, y1]) for (const z of [0, 28]) corners.push([x, y, z]);
  const unit = corners.map((c) => iso(c, { origin: [0, 0], scale: 1 }));
  const w = Math.max(...unit.map((p) => p[0])) - Math.min(...unit.map((p) => p[0]));
  const hgt = Math.max(...unit.map((p) => p[1])) - Math.min(...unit.map((p) => p[1]));
  const H = Math.round(Math.min(720, Math.max(320, (W * hgt) / w + 24)));
  return { P: fitProjection(corners, W, H - 34, { pad: 40 }), H };
}

const Station = memo(function Station({
  s, P, phase, active, selected, onPick,
}: { s: Placed; P: Projection; phase: number; active: boolean; selected: boolean; onPick: (id: string) => void }) {
  const parts = useMemo(() => station(s.type, P, s.cx, s.cy, active ? phase : 0), [s, P, phase, active]);
  return (
    <g
      className="mc-station"
      data-active={active || undefined}
      data-selected={selected || undefined}
      role="button"
      tabIndex={-1}
      aria-label={`${s.n}. ${s.name} (${ROLE_OF[s.type]})`}
      onClick={() => onPick(s.id)}
    >
      {parts.map((d, i) => <Draw key={i} d={d} lit={active || selected} />)}
    </g>
  );
});

function Label({ s, P, selected }: { s: Placed; P: Projection; selected: boolean }) {
  const [x, y] = iso([s.cx + PLINTH / 2, s.cy + PLINTH / 2, BASE_TOP], P);
  return (
    <text className="mc-label" data-selected={selected || undefined} x={x} y={y + 17} textAnchor="middle">
      <tspan className="mc-num">{String(s.n).padStart(2, "0")}</tspan> {s.name}
    </text>
  );
}

export function Machine({
  title, stages, links, selected, onSelect, autoRun = true, narration,
}: {
  title: string;
  stages: MachineStage[];
  links: MachineLink[];
  selected: string | null;
  onSelect: (id: string) => void;
  autoRun?: boolean;
  /** what Sherpa says: an opening line, then one line per stage (by stage id) */
  narration?: { intro?: string; lines: Record<string, string> };
}) {
  const { placed, routes, bounds } = useMemo(() => layout(stages, links), [stages, links]);
  const { P, H } = useMemo(() => fit(bounds), [bounds]);
  const routed: Routed[] = useMemo(() => links.map((l, i) => ({ ...l, runs: pipe(P, routes[i]) })), [links, routes, P]);

  // execution order: each stage, then the pipes leaving it
  const steps: Step[] = useMemo(
    () => placed.flatMap((s) => [
      { kind: "stage", id: s.id } as Step,
      ...links.flatMap((l, at) => (l.from === s.id ? [{ kind: "link", at } as Step] : [])),
    ]),
    [placed, links],
  );
  // step -1 is the spoken introduction, before any stage lights up
  const [run, setRun] = useState<{ step: number; phase: number; voice: boolean } | null>(null);
  const [caption, setCaption] = useState("");
  const raf = useRef(0);
  const runId = useRef(0); // bumps on every start and stop: an overtaken run ends itself
  const plate = useRef<HTMLDivElement>(null);

  const lineFor = (id: string) => {
    const s = placed.find((p) => p.id === id)!;
    return narration?.lines[id] || `${s.name}: the ${ROLE_OF[s.type].toLowerCase()} stage.`;
  };

  /** move the active stage's part (or light the pipe) until the next step starts */
  function animate(step: number, ms: number, withVoice: boolean) {
    cancelAnimationFrame(raf.current);
    const t0 = performance.now();
    const tick = (now: number) => {
      setRun({ step, phase: ((now - t0) % ms) / ms, voice: withVoice });
      raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
  }

  async function play(withVoice = false) {
    const mine = ++runId.current;
    const alive = () => mine === runId.current;
    const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
    // a voice that fails (no audio device, autoplay blocked) leaves the run going silently
    const speak = (text: string) => voice.say("machine", text).catch((e) => { if (!alive()) throw e; });
    if (withVoice) voice.stop(); // a silent run leaves other speech in the app alone
    const first = steps.find((s) => s.kind === "stage");
    if (withVoice) voice.preload([narration?.intro, first?.kind === "stage" ? lineFor(first.id) : ""].filter((t): t is string => !!t));
    try {
      if (withVoice && narration?.intro) {
        setRun({ step: -1, phase: 0, voice: true });
        setCaption(narration.intro);
        await speak(narration.intro);
      }
      for (let i = 0; i < steps.length; i++) {
        if (!alive()) return;
        const st = steps[i];
        if (st.kind === "stage") {
          onSelect(st.id);
          animate(i, STAGE_MS, withVoice);
          if (withVoice) {
            const line = lineFor(st.id);
            setCaption(line);
            const next = steps.slice(i + 1).find((x) => x.kind === "stage");
            if (next?.kind === "stage") voice.preload([lineFor(next.id)]); // ready when this line ends
            await Promise.all([speak(line), wait(STAGE_MS)]);
          } else await wait(STAGE_MS);
        } else {
          animate(i, LINK_MS, withVoice);
          await wait(LINK_MS);
        }
      }
    } catch {
      /* stopped */
    } finally {
      if (alive()) {
        cancelAnimationFrame(raf.current);
        setRun(null);
        setCaption("");
      }
    }
  }
  function stop() {
    runId.current++;
    cancelAnimationFrame(raf.current);
    if (run?.voice) voice.stop();
    setRun(null);
    setCaption("");
  }

  useEffect(() => {
    const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (autoRun && !still) void play(false);
    return () => {
      runId.current++;
      cancelAnimationFrame(raf.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [steps]);

  // stop (and go quiet) when the machine is scrolled away or its tab is hidden
  const running = useRef(false);
  running.current = !!run;
  useEffect(() => {
    const el = plate.current;
    if (!el || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting && running.current) {
        runId.current++;
        cancelAnimationFrame(raf.current);
        voice.stop();
        setRun(null);
        setCaption("");
      }
    });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  useEffect(() => () => { if (running.current) voice.stop(); }, []);

  const cur = run && run.step >= 0 ? steps[run.step] : null;
  const activeStage = cur?.kind === "stage" ? cur.id : null;
  const activeLink = cur?.kind === "link" ? cur.at : -1;

  // painter's order: base plate, then stations and pipe runs from far to near
  const items = useMemo(() => {
    const out: { depth: number; key: string; kind: "station" | "run"; s?: Placed; link?: number; run?: PipeRun }[] = [];
    placed.forEach((s) => out.push({ depth: depthAt(P, s.cx, s.cy), key: `s-${s.id}`, kind: "station", s }));
    routed.forEach((l, li) => l.runs.forEach((r, ri) => out.push({ depth: r.depth, key: `p-${li}-${ri}`, kind: "run", link: li, run: r })));
    return out.sort((a, b) => a.depth - b.depth);
  }, [placed, routed, P]);
  const base = useMemo(() => basePlate(P, bounds.x0, bounds.y0, bounds.x1, bounds.y1), [P, bounds]);

  const order = placed.map((s) => s.id);
  function onKey(e: KeyboardEvent) {
    const i = Math.max(0, order.indexOf(selected ?? ""));
    if (e.key === "ArrowRight" || e.key === "ArrowDown") onSelect(order[Math.min(order.length - 1, i + 1)]);
    else if (e.key === "ArrowLeft" || e.key === "ArrowUp") onSelect(order[Math.max(0, i - 1)]);
    else if (e.key === " " || e.key === "Enter") (run ? stop() : void play(false));
    else if (e.key.toLowerCase() === "n") (run ? stop() : void play(true));
    else return;
    e.preventDefault();
  }

  const loops = links.filter((l) => l.loop).length;
  const sel = placed.find((s) => s.id === selected);
  const readout = run?.step === -1 ? "introduction" : cur
    ? cur.kind === "stage"
      ? `step ${placed.findIndex((s) => s.id === cur.id) + 1}/${placed.length} · ${ROLE_OF[placed.find((s) => s.id === cur.id)!.type]}`
      : `${links[cur.at].loop ? "loops back" : "hands on"}${links[cur.at].label ? ` · ${links[cur.at].label}` : ""}`
    : sel
      ? `${String(sel.n).padStart(2, "0")} · ${ROLE_OF[sel.type]}`
      : `${placed.length} stages${loops ? ` · ${loops} loop${loops > 1 ? "s" : ""}` : ""}`;

  return (
    <div ref={plate} className="iso mc-plate" tabIndex={0} onKeyDown={onKey}
      aria-label={`${title}: pipeline machine. Arrow keys pick a stage, space runs it, N runs it with narration.`}>
      <div className="mc-corner" data-corner="fig">Fig. 1</div>
      <div className="mc-corner" data-corner="title">{title}</div>
      <svg className="iso-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${placed.length} stages`}>
        {base.map((d, i) => <Draw key={i} d={d} lit={false} />)}
        {items.map((it) =>
          it.kind === "station" ? (
            <Station key={it.key} s={it.s!} P={P} phase={activeStage === it.s!.id ? run!.phase : 0}
              active={activeStage === it.s!.id} selected={selected === it.s!.id} onPick={onSelect} />
          ) : (
            <g key={it.key} className="mc-pipe" data-loop={routed[it.link!].loop || undefined}>
              <Draw d={{ t: "solid", p: it.run!.solid, tone: "mid", accent: true }} lit={activeLink === it.link} />
              <path className="iso-line" data-tone={activeLink === it.link ? "lit" : routed[it.link!].loop ? "lo" : "faint"}
                data-flow={activeLink === it.link || undefined} data-dashed={routed[it.link!].loop || undefined} d={it.run!.flow} />
            </g>
          ),
        )}
        {placed.map((s) => <Label key={s.id} s={s} P={P} selected={selected === s.id} />)}
      </svg>
      {caption && <p className="mc-caption" aria-live="polite">{caption}</p>}
      <div className="mc-corner" data-corner="hint">
        {run ? (
          <button type="button" className="mc-run" onClick={stop}>■ Stop</button>
        ) : (
          <>
            <button type="button" className="mc-run" onClick={() => void play(false)}>▶ Run</button>
            <button type="button" className="mc-run" data-quiet="" onClick={() => void play(true)} title="Run it while Sherpa explains each stage (N)">
              🔊 Narrate
            </button>
          </>
        )}
        <span className="mc-hint">click a part · ← → · space</span>
      </div>
      <div className="mc-corner" data-corner="readout" aria-live="polite">{readout}</div>
    </div>
  );
}
