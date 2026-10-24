/* Renders one machine-parts Drawable as SVG, with Anatomy's iso-* classes (styled in globals.css). */
import type { Drawable } from "./machine-parts";

export function Draw({ d, lit }: { d: Drawable; lit: boolean }) {
  if (d.t === "line") {
    if (!d.d) return null;
    return <path className="iso-line" data-tone={lit && d.accent ? "lit" : d.tone} d={d.d} />;
  }
  if (d.t === "dots") {
    return (
      <g className="iso-dots" data-tone={d.tone}>
        {d.pts.map(([x, y], i) => <circle key={i} cx={x} cy={y} r={1.3} />)}
      </g>
    );
  }
  const p = d.p;
  return (
    <g className="iso-solid" data-lit={lit && d.accent ? "" : undefined}>
      {d.halo && <path className="iso-halo" d={p.fill} />}
      <path className="iso-fill" d={p.fill} />
      {!d.flat && p.shades.map((s, i) => s && <path key={i} className="iso-shade" data-shade={i} d={s} />)}
      {!d.flat && <path className="iso-top" d={p.top} />}
      {p.crease && <path className="iso-line" data-tone="faint" d={p.crease} />}
      {p.bevel && <path className="iso-line" data-tone="faint" d={p.bevel} />}
      <path className="iso-line" data-tone={lit && d.accent ? "lit" : d.tone} d={p.outline} />
    </g>
  );
}
