"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Building2, FileCode2, MessageSquare, Pause, Play, RefreshCw, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, type City } from "../../lib/api";
import { useCodeViewer } from "../code-viewer";
import { CityView, PLAY_MS, type HeatMode } from "../machine/city";
import { Button } from "../ui/primitives";
import { cn } from "../../lib/utils";
import { EmptyState, FadeIn, SectionLabel } from "./shared";

const HEAT: { id: HeatMode; label: string }[] = [
  { id: "changes", label: "Most changed" },
  { id: "recent", label: "Recently changed" },
  { id: "none", label: "Plain" },
];

const date = (t: number) => new Date(t * 1000).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
const name = (p: string) => p.split("/").pop() ?? p;

export function CityPanel({
  repoId,
  busy,
  setBusy,
  onAsk,
}: {
  repoId: string;
  busy: string | null;
  setBusy: (v: string | null) => void;
  onAsk: (q: string) => void;
}) {
  const [city, setCity] = useState<City | null>(null);
  const [heat, setHeat] = useState<HeatMode>("changes");
  const [selected, setSelected] = useState<number | null>(null);
  const [hover, setHover] = useState<{ i: number; x: number; y: number } | null>(null);
  const [frame, setFrame] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const { open } = useCodeViewer();

  async function build(refresh = false) {
    setBusy("city");
    try {
      const c = await api.city(repoId, refresh);
      setCity(c);
      setSelected(null);
      setFrame(null);
      setPlaying(false);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to build the city");
    } finally {
      setBusy(null);
    }
  }

  const frames = city?.timeline.length ?? 0;
  // play: one frame per tick, the whole history in about PLAY_MS
  useEffect(() => {
    if (!playing || !frames) return;
    if (frame != null && frame >= frames - 1) {
      // hold on the last commit for a moment, then back to today
      const t = window.setTimeout(() => (setPlaying(false), setFrame(null)), 1400);
      return () => window.clearTimeout(t);
    }
    const t = window.setTimeout(() => setFrame((f) => (f ?? -1) + 1), Math.max(45, Math.min(500, PLAY_MS / frames)));
    return () => window.clearTimeout(t);
  }, [playing, frame, frames]);

  const deps = useMemo(() => {
    if (!city || selected == null) return { uses: [] as number[], usedBy: [] as number[] };
    return {
      uses: city.edges.filter(([a]) => a === selected).map(([, b]) => b),
      usedBy: city.edges.filter(([, b]) => b === selected).map(([a]) => a),
    };
  }, [city, selected]);

  // the code files that churn most (release notes and lockfiles would crowd them out), else the biggest
  const hot = useMemo(() => {
    if (!city) return [];
    const code = city.buildings.map((b, i) => ({ b, i })).filter((x) => city.districts[x.b.district]?.code);
    const pool = code.length ? code : city.buildings.map((b, i) => ({ b, i }));
    return pool.filter((x) => x.b.changes > 0).sort((a, b) => b.b.changes - a.b.changes).slice(0, 6);
  }, [city]);
  const biggest = useMemo(
    () => (city ? city.buildings.map((b, i) => ({ b, i })).sort((a, b) => b.b.lines - a.b.lines).slice(0, 6) : []),
    [city],
  );

  if (!city) {
    return (
      <div className="scroll-thin flex-1 overflow-y-auto p-6">
        <EmptyState
          busy={busy === "city"}
          pose="analyzing"
          title="Repo City"
          body="See the whole codebase as a city: every file a building (taller = more code), every component a district, glowing where the code changes most. Play the time-lapse to watch it grow commit by commit."
        >
          <Button onClick={() => build()} disabled={!repoId || !!busy}>
            <Building2 className="size-4" />
            {busy === "city" ? "Building the city…" : "Build the city"}
          </Button>
          {!repoId && <p className="text-xs text-muted-foreground">Index a repo first.</p>}
        </EmptyState>
      </div>
    );
  }

  const sel = selected != null ? city.buildings[selected] : null;
  const fr = frame != null ? city.timeline[frame] : null;
  const hov = hover ? city.buildings[hover.i] : null;
  const box = wrap.current?.getBoundingClientRect();

  return (
    <div className="scroll-thin flex-1 overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-5 p-4 sm:p-6">
        <FadeIn>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="mr-auto text-lg font-semibold">Repo City</h2>
            <div role="radiogroup" aria-label="Color buildings by" className="flex rounded-lg border border-border bg-card p-0.5 text-[12px]">
              {HEAT.map((h) => (
                <button
                  key={h.id}
                  role="radio"
                  aria-checked={heat === h.id}
                  onClick={() => setHeat(h.id)}
                  className={cn("rounded-md px-2.5 py-1", heat === h.id ? "bg-secondary font-medium text-foreground" : "text-muted-foreground hover:text-foreground")}
                >
                  {h.label}
                </button>
              ))}
            </div>
            <Button size="sm" variant="ghost" onClick={() => build(true)} disabled={!!busy}>
              <RefreshCw className={cn("size-3.5", busy === "city" && "animate-spin")} /> Rebuild
            </Button>
          </div>
          <p className="mt-1.5 text-[13px] tabular-nums text-muted-foreground">
            {city.stats.drawn} of {city.stats.files} files · {city.districts.length} districts ·{" "}
            {city.stats.lines.toLocaleString()} lines
            {city.history !== "none" && <> · {frames} commits{city.history === "recent" ? " (most recent)" : ""}</>}
          </p>
        </FadeIn>

        <FadeIn delay={0.05} className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
          <div ref={wrap} className="iso mc-plate city-plate" onPointerLeave={() => setHover(null)}>
            <div className="mc-corner" data-corner="fig">Fig. 2</div>
            <div className="mc-corner" data-corner="title">{fr ? date(fr.t) : "Today"}</div>
            <CityView
              city={city}
              heat={heat}
              selected={selected}
              onSelect={setSelected}
              frame={frame}
              onHover={(i, at) => setHover(i == null || !at ? null : { i, ...at })}
            />
            {hov && hover && box && (
              <div
                className="pointer-events-none absolute z-10 max-w-[260px] rounded-md border border-border bg-popover px-2.5 py-1.5 text-[12px] shadow-md"
                style={{ left: Math.min(hover.x - box.left + 14, box.width - 230), top: hover.y - box.top + 14 }}
              >
                <p className="truncate font-mono font-medium">{hov.path}</p>
                <p className="tabular-nums text-muted-foreground">
                  {hov.lines} lines{hov.defs ? ` · ${hov.defs} definitions` : ""}
                  {hov.changes ? ` · changed ${hov.changes}×` : ""}
                </p>
              </div>
            )}
            <div className="city-bar">
              {frames > 1 ? (
                <>
                  <button
                    type="button"
                    className="mc-run"
                    onClick={() => {
                      if (playing) return setPlaying(false);
                      if (frame == null || frame >= frames - 1) setFrame(0);
                      setPlaying(true);
                    }}
                    aria-label={playing ? "Pause the time-lapse" : "Play the time-lapse"}
                  >
                    {playing ? <Pause className="inline size-3" /> : <Play className="inline size-3" />} {playing ? "Pause" : "Time-lapse"}
                  </button>
                  <input
                    type="range"
                    min={0}
                    max={frames}
                    value={frame ?? frames}
                    aria-label="Commit"
                    onChange={(e) => {
                      const v = Number(e.target.value);
                      setPlaying(false);
                      setFrame(v >= frames ? null : v);
                    }}
                    className="city-scrub"
                  />
                  {frame != null && (
                    <button type="button" className="city-today" onClick={() => (setPlaying(false), setFrame(null))} aria-label="Back to today">
                      <RotateCcw className="size-3" />
                    </button>
                  )}
                </>
              ) : (
                <span className="mc-hint">No commit history for this source</span>
              )}
            </div>
            <div className="city-ticker" aria-live="polite">
              {fr ? (
                <>
                  <span className="tabular-nums">{String(frame! + 1).padStart(String(frames).length, "0")}/{frames}</span>
                  <span className="truncate">{fr.subject}</span>
                  <span className="shrink-0 tabular-nums">{fr.changed.length} file{fr.changed.length === 1 ? "" : "s"}</span>
                </>
              ) : (
                <>
                  <span className="mc-hint city-hint-wide">click a building · scroll or double-click to zoom · drag to pan</span>
                  <span className="mc-hint city-hint-narrow">tap a building · double-tap to zoom</span>
                </>
              )}
            </div>
          </div>

          <aside className="flex flex-col gap-3 self-start">
            {sel ? (
              <div className="rounded-xl border border-border bg-card">
                <div className="p-4">
                  <p className="eyebrow">{city.districts[sel.district]?.name}</p>
                  <h3 className="mt-1 break-all font-mono text-[14px] font-semibold">{sel.path}</h3>
                  <dl className="mt-3 grid grid-cols-2 gap-y-1.5 text-[12px] tabular-nums">
                    <dt className="text-muted-foreground">Lines</dt><dd>{sel.lines.toLocaleString()}</dd>
                    {sel.defs > 0 && (<><dt className="text-muted-foreground">Definitions</dt><dd>{sel.defs}</dd></>)}
                    {city.history !== "none" && (<><dt className="text-muted-foreground">Changed</dt><dd>{sel.changes}× in {frames} commits</dd></>)}
                    {sel.last && (<><dt className="text-muted-foreground">Last change</dt><dd>{date(sel.last)}</dd></>)}
                    <dt className="text-muted-foreground">Imports</dt><dd>{deps.uses.length} file{deps.uses.length === 1 ? "" : "s"}</dd>
                    <dt className="text-muted-foreground">Imported by</dt><dd>{deps.usedBy.length} file{deps.usedBy.length === 1 ? "" : "s"}</dd>
                  </dl>
                  {deps.usedBy.length > 0 && (
                    <>
                      <p className="mt-3 text-[11px] uppercase tracking-wide text-muted-foreground">A change here can affect</p>
                      <ul className="mt-1 space-y-0.5">
                        {deps.usedBy.slice(0, 8).map((i) => (
                          <li key={i}>
                            <button className="truncate font-mono text-[12px] text-primary hover:underline" onClick={() => setSelected(i)}>
                              {city.buildings[i].path}
                            </button>
                          </li>
                        ))}
                        {deps.usedBy.length > 8 && <li className="text-[12px] text-muted-foreground">and {deps.usedBy.length - 8} more</li>}
                      </ul>
                    </>
                  )}
                </div>
                <div className="flex gap-2 border-t border-border p-3">
                  <Button size="sm" variant="outline" className="flex-1" onClick={() => open(sel.path, 1, Math.min(sel.lines, 60) || 1)}>
                    <FileCode2 className="size-3.5" /> Open file
                  </Button>
                  <Button size="sm" onClick={() => onAsk(`What does ${sel.path} do, and what would I need to check before changing it?`)}>
                    <MessageSquare className="size-3.5" /> Ask
                  </Button>
                </div>
              </div>
            ) : (
              <div className="rounded-xl border border-border bg-card p-4">
                <SectionLabel>{hot.length ? "Changes most often" : "Biggest files"}</SectionLabel>
                <ul className="space-y-1">
                  {(hot.length ? hot : biggest).map(({ b, i }) => (
                    <li key={i} className="flex items-baseline gap-2 text-[12px]">
                      <button className="min-w-0 flex-1 truncate text-left font-mono text-primary hover:underline" onClick={() => setSelected(i)} title={b.path}>
                        {name(b.path)}
                      </button>
                      <span className="shrink-0 tabular-nums text-muted-foreground">{hot.length ? `${b.changes}×` : `${b.lines} lines`}</span>
                    </li>
                  ))}
                </ul>
                <p className="mt-3 text-[12px] text-muted-foreground">Pick a building to see what a change there can affect.</p>
              </div>
            )}
            <div className="rounded-xl border border-border bg-card p-4 text-[12px] text-muted-foreground">
              <SectionLabel>Reading the city</SectionLabel>
              <ul className="space-y-1">
                <li><span className="font-medium text-foreground">Height</span> = lines of code</li>
                <li><span className="font-medium text-foreground">Width</span> = functions and classes</li>
                <li><span className="font-medium text-foreground">Blue</span> = {heat === "recent" ? "changed recently" : heat === "changes" ? "changed often" : "off"}</li>
                <li><span className="font-medium text-foreground">Low-rise</span> = docs and config</li>
                <li><span className="font-medium text-foreground">Arcs</span> = imports (dashed: imported by)</li>
              </ul>
            </div>
          </aside>
        </FadeIn>
      </div>
    </div>
  );
}
