import React from "react";
import {
  AbsoluteFill,
  interpolate,
  Sequence,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

/* ─── Design tokens ──────────────────────────────────────────── */
const C = {
  bg: "#030303",
  fg: "#f0f0f0",
  dim: "#666",
  muted: "#2a2a2a",
  blue: "#4a9eff",
  violet: "#7c3aed",
  border: "#141414",
  card: "#0b0b0b",
  green: "#22c55e",
  white: "#ffffff",
};

/* ─── 11-dot orb cluster ─────────────────────────────────────── */
const DOTS = [
  { x: 0.500, y: 0.500, r: 1.40, op: 1.00, ph: 0.00, spd: 1.00 }, // center
  { x: 0.500, y: 0.155, r: 0.88, op: 0.90, ph: 0.79, spd: 0.90 }, // top
  { x: 0.815, y: 0.278, r: 0.82, op: 0.82, ph: 1.57, spd: 1.10 }, // top-right
  { x: 0.878, y: 0.618, r: 0.73, op: 0.68, ph: 2.36, spd: 0.80 }, // right
  { x: 0.652, y: 0.872, r: 0.79, op: 0.72, ph: 3.14, spd: 1.20 }, // bottom-right
  { x: 0.348, y: 0.872, r: 0.79, op: 0.72, ph: 3.93, spd: 0.95 }, // bottom-left
  { x: 0.122, y: 0.618, r: 0.73, op: 0.62, ph: 4.71, spd: 1.05 }, // left
  { x: 0.185, y: 0.278, r: 0.82, op: 0.76, ph: 5.50, spd: 0.85 }, // top-left
  { x: 0.500, y: 0.318, r: 0.55, op: 0.50, ph: 1.20, spd: 1.30 }, // inner-top
  { x: 0.673, y: 0.673, r: 0.50, op: 0.44, ph: 2.80, spd: 1.15 }, // inner-br
  { x: 0.327, y: 0.673, r: 0.50, op: 0.44, ph: 3.60, spd: 0.90 }, // inner-bl
];

type OrbState = "idle" | "thinking" | "responding";

/* ─── Sherpa orb (pure frame-math, no Framer Motion) ────────── */
function SherpaOrbVideo({
  size,
  frame,
  state = "idle",
  glow = 1,
}: {
  size: number;
  frame: number;
  state?: OrbState;
  glow?: number;
}) {
  const c = size / 2;
  const baseR = size * 0.047;
  const t = frame / 30;
  const uid = `o${Math.round(size)}`;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ overflow: "visible" }}>
      <defs>
        <filter id={`${uid}-g`} x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur in="SourceGraphic" stdDeviation={baseR * 1.5} result="wide" />
          <feGaussianBlur in="SourceGraphic" stdDeviation={baseR * 0.35} result="tight" />
          <feMerge>
            <feMergeNode in="wide" />
            <feMergeNode in="tight" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <radialGradient id={`${uid}-bg`} cx="50%" cy="40%" r="55%">
          <stop offset="0%" stopColor={C.blue} stopOpacity={0.10 * glow} />
          <stop offset="55%" stopColor={C.violet} stopOpacity={0.04 * glow} />
          <stop offset="100%" stopColor={C.blue} stopOpacity={0} />
        </radialGradient>
      </defs>

      {/* Ambient halo */}
      <circle cx={c} cy={c} r={c * 0.94} fill={`url(#${uid}-bg)`} />

      {/* Breathing ring */}
      <circle
        cx={c} cy={c} r={c * 0.77}
        fill="none"
        stroke={C.blue}
        strokeWidth={size * 0.0022}
        opacity={Math.max(0, 0.06 * glow + Math.sin(t * 1.3) * 0.02)}
      />

      {DOTS.map((d, i) => {
        const cx0 = d.x * size;
        const cy0 = d.y * size;
        const r = baseR * d.r;
        let cx = cx0, cy = cy0, op = d.op;

        if (state === "idle") {
          const ph = d.ph + t * d.spd;
          cx += Math.sin(ph) * size * 0.014;
          cy += Math.cos(ph * 1.31 + d.ph * 0.38) * size * 0.014;
          op *= 0.80 + Math.sin(ph * 0.62 + i * 0.4) * 0.20;
        } else if (state === "thinking") {
          const ang = (frame / 40) * Math.PI * 2 * d.spd;
          const rx = cx0 - c, ry = cy0 - c;
          cx = c + rx * Math.cos(ang) - ry * Math.sin(ang);
          cy = c + rx * Math.sin(ang) + ry * Math.cos(ang);
          op *= 0.50 + Math.sin(frame / 8 + i * 0.8) * 0.50;
        } else {
          const pulse = 1 + Math.sin(frame / 14) * 0.06;
          cx = c + (cx0 - c) * pulse;
          cy = c + (cy0 - c) * pulse;
          op *= 0.88 + Math.sin(frame / 10 + i) * 0.12;
        }

        return (
          <circle
            key={i}
            cx={cx} cy={cy} r={r}
            fill={i % 5 === 4 ? C.violet : C.blue}
            opacity={Math.min(1, Math.max(0, op))}
            filter={`url(#${uid}-g)`}
          />
        );
      })}
    </svg>
  );
}

/* ─── Scale helper (1.0 at 1080p, 2.0 at 4K) ────────────────── */
function useScale() {
  const { height } = useVideoConfig();
  return height / 1080;
}

/* ─── Clamped interpolate ────────────────────────────────────── */
function lerp(frame: number, range: [number, number], output: [number, number]) {
  return interpolate(frame, range, output, {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
}

/* ─── Animated film grain ────────────────────────────────────── */
function Grain({ opacity = 0.04 }: { opacity?: number }) {
  const { width, height } = useVideoConfig();
  const frame = useCurrentFrame();
  const bf = 0.62 + (frame % 60) * 0.003;
  return (
    <svg
      width={width} height={height}
      style={{ position: "absolute", inset: 0, pointerEvents: "none" }}
    >
      <defs>
        <filter id="grain-f">
          <feTurbulence type="fractalNoise" baseFrequency={bf} numOctaves={4} stitchTiles="stitch" result="n" />
          <feColorMatrix type="saturate" values="0" in="n" />
        </filter>
      </defs>
      <rect width={width} height={height} filter="url(#grain-f)" opacity={opacity} />
    </svg>
  );
}

/* ─── Subtle dot grid ────────────────────────────────────────── */
function Grid({ opacity = 0.28 }: { opacity?: number }) {
  const { width, height } = useVideoConfig();
  const s = useScale();
  const sz = Math.round(80 * s);
  return (
    <div style={{
      position: "absolute", inset: 0, pointerEvents: "none",
      backgroundImage: `radial-gradient(circle, ${C.border} 1px, transparent 1px)`,
      backgroundSize: `${sz}px ${sz}px`,
      backgroundPosition: `${sz / 2}px ${sz / 2}px`,
      opacity,
    }} />
  );
}

/* ══════════════════════════════════════════════════════════════
   Scene 1 — Intro  (0–150f, 0–5s)
   Orb materialises from nothing. Title drops in.
══════════════════════════════════════════════════════════════ */
function SceneIntro() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = useScale();

  const orbScale = spring({ frame, fps, config: { damping: 18, stiffness: 52, mass: 1 } });
  const orbOp = lerp(frame, [0, 22], [0, 1]);

  const titleOp = lerp(frame, [52, 88], [0, 1]);
  const titleY = lerp(frame, [52, 88], [18 * s, 0]);
  const subOp = lerp(frame, [76, 108], [0, 1]);

  return (
    <AbsoluteFill style={{ background: C.bg, alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 44 * s }}>
      <Grain />
      <Grid opacity={0.22} />
      <div style={{
        position: "absolute", inset: 0,
        background: `radial-gradient(ellipse 48% 42% at 50% 50%, ${C.blue}13 0%, transparent 68%)`,
      }} />

      <div style={{ opacity: orbOp, transform: `scale(${orbScale})`, zIndex: 1 }}>
        <SherpaOrbVideo size={280 * s} frame={frame} state="idle" glow={1.2} />
      </div>

      <div style={{ opacity: titleOp, transform: `translateY(${titleY}px)`, textAlign: "center", zIndex: 1 }}>
        <div style={{
          fontFamily: '"Geist", "Inter", -apple-system, BlinkMacSystemFont, sans-serif',
          fontSize: 92 * s, fontWeight: 600, color: C.fg,
          letterSpacing: -3.5 * s, lineHeight: 1.0,
        }}>
          Meet Sherpa.
        </div>
      </div>

      <div style={{ opacity: subOp, textAlign: "center", zIndex: 1 }}>
        <div style={{
          fontFamily: '"Geist", "Inter", -apple-system, sans-serif',
          fontSize: 27 * s, fontWeight: 400, color: C.dim,
          letterSpacing: -0.4 * s,
        }}>
          Your AI guide through any codebase.
        </div>
      </div>
    </AbsoluteFill>
  );
}

/* ══════════════════════════════════════════════════════════════
   Scene 2 — Problem  (150–300f, 5–10s)
   The unfamiliar codebase.
══════════════════════════════════════════════════════════════ */
function SceneProblem() {
  const frame = useCurrentFrame();
  const s = useScale();
  const sceneOp = lerp(frame, [0, 22], [0, 1]);

  const lines = ["Every new codebase", "is unfamiliar territory."];
  const bullets = [
    "Hundreds of files. No map.",
    "Dependencies you've never seen.",
    "No one to ask at 2 AM.",
  ];

  return (
    <AbsoluteFill style={{ background: C.bg, opacity: sceneOp }}>
      <Grain />
      <div style={{
        position: "absolute", inset: 0,
        background: `radial-gradient(ellipse 55% 45% at 28% 52%, ${C.blue}09 0%, transparent 58%)`,
      }} />

      <div style={{
        position: "absolute", left: 130 * s, top: "50%",
        transform: "translateY(-50%)",
        display: "flex", flexDirection: "column", gap: 0,
        maxWidth: 720 * s,
      }}>
        {lines.map((line, i) => {
          const op = lerp(frame, [18 + i * 16, 48 + i * 16], [0, 1]);
          const y = lerp(frame, [18 + i * 16, 48 + i * 16], [22 * s, 0]);
          return (
            <div key={i} style={{
              opacity: op, transform: `translateY(${y}px)`,
              fontFamily: '"Geist", "Inter", -apple-system, sans-serif',
              fontSize: 74 * s, fontWeight: 600,
              color: i === 0 ? C.fg : C.dim,
              letterSpacing: -2.5 * s, lineHeight: 1.1,
            }}>
              {line}
            </div>
          );
        })}

        <div style={{ marginTop: 48 * s, display: "flex", flexDirection: "column", gap: 18 * s }}>
          {bullets.map((b, i) => {
            const op = lerp(frame, [68 + i * 18, 92 + i * 18], [0, 1]);
            const x = lerp(frame, [68 + i * 18, 92 + i * 18], [-22 * s, 0]);
            return (
              <div key={i} style={{
                opacity: op, transform: `translateX(${x}px)`,
                display: "flex", alignItems: "center", gap: 14 * s,
              }}>
                <div style={{
                  width: 6 * s, height: 6 * s, borderRadius: "50%",
                  background: C.blue, flexShrink: 0, opacity: 0.7,
                }} />
                <div style={{
                  fontFamily: '"Geist", "Inter", -apple-system, sans-serif',
                  fontSize: 23 * s, fontWeight: 400, color: C.dim,
                  letterSpacing: -0.3 * s,
                }}>
                  {b}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Ghost orb, right */}
      <div style={{
        position: "absolute", right: 160 * s, top: "50%",
        transform: "translateY(-50%)",
        opacity: lerp(frame, [82, 115], [0, 0.35]),
      }}>
        <SherpaOrbVideo size={190 * s} frame={frame} state="idle" glow={0.55} />
      </div>
    </AbsoluteFill>
  );
}

/* ══════════════════════════════════════════════════════════════
   Scene 3 — Ask  (300–450f, 10–15s)
   A single question. Orb shifts to thinking.
══════════════════════════════════════════════════════════════ */
function SceneAsk() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = useScale();

  const sceneOp = lerp(frame, [0, 18], [0, 1]);
  const orbScale = spring({ frame, fps, config: { damping: 14, stiffness: 46 } });

  const question = "How does user authentication work?";
  const charsVisible = Math.floor(lerp(frame, [22, 85], [0, question.length]));
  const cursorOn = frame < 98 && Math.floor(frame / 8) % 2 === 0;

  return (
    <AbsoluteFill style={{ background: C.bg, opacity: sceneOp, alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 58 * s }}>
      <Grain />
      <div style={{
        position: "absolute", inset: 0,
        background: `radial-gradient(ellipse 52% 44% at 50% 46%, ${C.blue}11 0%, transparent 64%)`,
      }} />

      <div style={{ transform: `scale(${orbScale})`, zIndex: 1 }}>
        <SherpaOrbVideo
          size={230 * s} frame={frame}
          state={frame > 92 ? "thinking" : "idle"}
          glow={1.1}
        />
      </div>

      {/* Typed question bubble */}
      <div style={{
        opacity: lerp(frame, [14, 38], [0, 1]),
        transform: `translateY(${lerp(frame, [14, 38], [14 * s, 0])}px)`,
        zIndex: 1,
        background: C.white,
        borderRadius: 22 * s,
        padding: `${22 * s}px ${36 * s}px`,
        maxWidth: 660 * s,
      }}>
        <div style={{
          fontFamily: '"Geist", "Inter", -apple-system, sans-serif',
          fontSize: 25 * s, fontWeight: 500, color: "#000",
          letterSpacing: -0.4 * s, minHeight: 30 * s,
        }}>
          {question.slice(0, charsVisible)}
          {cursorOn && (
            <span style={{
              display: "inline-block", width: 2.5 * s, height: 24 * s,
              background: "#000", marginLeft: 2 * s, verticalAlign: "middle",
            }} />
          )}
        </div>
      </div>
    </AbsoluteFill>
  );
}

/* ══════════════════════════════════════════════════════════════
   Scene 4 — Answer  (450–690f, 15–23s)
   Sherpa's grounded answer materialises line-by-line.
══════════════════════════════════════════════════════════════ */
function SceneAnswer() {
  const frame = useCurrentFrame();
  const s = useScale();
  const sceneOp = lerp(frame, [0, 18], [0, 1]);

  const answerLines = [
    "Auth flows through POST /api/auth/login.",
    "Credentials validated with bcrypt,",
    "then a 24-hour JWT is signed and returned.",
  ];

  const sources = [
    "app/routers/auth.py:38–44",
    "app/security.py:22–33",
    "app/models/user.py:12–34",
  ];

  return (
    <AbsoluteFill style={{ background: C.bg, opacity: sceneOp }}>
      <Grain />
      <div style={{
        position: "absolute", inset: 0,
        background: `radial-gradient(ellipse 48% 42% at 62% 50%, ${C.violet}08 0%, transparent 58%)`,
      }} />

      {/* Left: orb + label */}
      <div style={{
        position: "absolute", left: 100 * s, top: "50%",
        transform: "translateY(-50%)",
        display: "flex", flexDirection: "column", alignItems: "center", gap: 18 * s,
        opacity: lerp(frame, [0, 28], [0, 1]),
      }}>
        <SherpaOrbVideo size={168 * s} frame={frame} state="responding" glow={1.15} />
        <div style={{
          fontFamily: '"Geist", "Inter", -apple-system, sans-serif',
          fontSize: 17 * s, fontWeight: 600, color: C.fg, letterSpacing: -0.2 * s,
        }}>Sherpa</div>
        <div style={{
          fontFamily: '"Geist", "Inter", -apple-system, sans-serif',
          fontSize: 13 * s, color: C.dim, letterSpacing: 0,
        }}>AI Codebase Guide</div>
      </div>

      {/* Right: answer card */}
      <div style={{
        position: "absolute",
        left: 350 * s, right: 90 * s, top: "50%",
        transform: "translateY(-50%)",
      }}>
        <div style={{
          background: C.card,
          border: `1px solid ${C.border}`,
          borderRadius: 22 * s,
          overflow: "hidden",
        }}>
          {/* Answer text */}
          <div style={{ padding: `${30 * s}px ${34 * s}px` }}>
            {answerLines.map((line, i) => {
              const op = lerp(frame, [28 + i * 24, 58 + i * 24], [0, 1]);
              const x = lerp(frame, [28 + i * 24, 58 + i * 24], [-14 * s, 0]);
              return (
                <div key={i} style={{
                  opacity: op, transform: `translateX(${x}px)`,
                  fontFamily: '"Geist", "Inter", -apple-system, sans-serif',
                  fontSize: 23 * s, fontWeight: 400, color: C.fg,
                  lineHeight: 1.68, letterSpacing: -0.25 * s,
                }}>
                  {line}
                </div>
              );
            })}
          </div>

          {/* Citation chips */}
          <div style={{
            borderTop: `1px solid ${C.border}`,
            padding: `${18 * s}px ${34 * s}px`,
            display: "flex", gap: 10 * s, flexWrap: "wrap",
          }}>
            {sources.map((src, i) => {
              const op = lerp(frame, [122 + i * 18], [0, 1]);
              const chipOp = lerp(frame, [122 + i * 18, 150 + i * 18], [0, 1]);
              const chipY = lerp(frame, [122 + i * 18, 150 + i * 18], [8 * s, 0]);
              return (
                <div key={src} style={{
                  opacity: chipOp, transform: `translateY(${chipY}px)`,
                  background: "#0f0f0f",
                  border: `1px solid ${C.border}`,
                  borderRadius: 9 * s,
                  padding: `${6 * s}px ${13 * s}px`,
                  fontFamily: '"Geist Mono", "JetBrains Mono", "SF Mono", Menlo, monospace',
                  fontSize: 13 * s, color: C.dim,
                }}>
                  {src}
                </div>
              );
            })}
          </div>
        </div>

        {/* Verified badge */}
        <div style={{
          opacity: lerp(frame, [185, 205], [0, 1]),
          marginTop: 18 * s,
          display: "flex", alignItems: "center", gap: 9 * s,
        }}>
          <div style={{
            width: 8 * s, height: 8 * s, borderRadius: "50%", background: C.green,
          }} />
          <div style={{
            fontFamily: '"Geist", "Inter", -apple-system, sans-serif',
            fontSize: 14 * s, fontWeight: 500, color: C.green,
          }}>
            Verified — all citations confirmed in repo
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
}

/* ══════════════════════════════════════════════════════════════
   Scene 5 — Features  (690–810f, 23–27s)
   Three quick-dissolve feature beats.
══════════════════════════════════════════════════════════════ */
function FeatureBeat({
  icon,
  title,
  desc,
  startFrame,
}: {
  icon: string;
  title: string;
  desc: string;
  startFrame: number;
}) {
  const frame = useCurrentFrame();
  const s = useScale();
  const lf = frame - startFrame;
  const fadeIn = lerp(lf, [0, 18], [0, 1]);
  const fadeOut = lerp(lf, [30, 44], [1, 0]);
  const y = lerp(lf, [0, 18], [14 * s, 0]);

  return (
    <div style={{ opacity: fadeIn * fadeOut, transform: `translateY(${y}px)`, textAlign: "center" }}>
      <div style={{ fontSize: 60 * s, lineHeight: 1, marginBottom: 14 * s }}>{icon}</div>
      <div style={{
        fontFamily: '"Geist", "Inter", -apple-system, sans-serif',
        fontSize: 58 * s, fontWeight: 600, color: C.fg,
        letterSpacing: -2.2 * s, lineHeight: 1.0,
      }}>
        {title}
      </div>
      <div style={{
        fontFamily: '"Geist", "Inter", -apple-system, sans-serif',
        fontSize: 23 * s, color: C.dim, marginTop: 14 * s,
        letterSpacing: -0.2 * s,
      }}>
        {desc}
      </div>
    </div>
  );
}

function SceneFeatures() {
  const frame = useCurrentFrame();
  const s = useScale();

  const beats = [
    { icon: "🗺️", title: "Architecture maps.", desc: "Component roles. Import edges. At a glance.", start: 0 },
    { icon: "🧭", title: "Guided tours.", desc: "Trace any feature, step by step.", start: 38 },
    { icon: "✅", title: "Starter tasks.", desc: "First PRs from your actual repo.", start: 76 },
  ];

  return (
    <AbsoluteFill style={{ background: C.bg, alignItems: "center", justifyContent: "center" }}>
      <Grain />
      <div style={{
        position: "absolute", inset: 0,
        background: `radial-gradient(ellipse 52% 44% at 50% 50%, ${C.blue}0b 0%, transparent 62%)`,
      }} />
      {beats.map((b) => {
        if (frame < b.start || frame >= b.start + 44) return null;
        return (
          <div key={b.title} style={{ position: "absolute", zIndex: 1, padding: `0 ${120 * s}px`, width: "100%", boxSizing: "border-box" }}>
            <FeatureBeat icon={b.icon} title={b.title} desc={b.desc} startFrame={b.start} />
          </div>
        );
      })}
    </AbsoluteFill>
  );
}

/* ══════════════════════════════════════════════════════════════
   Scene 6 — CTA  (810–900f, 27–30s)
   Any repo. No setup. Free.
══════════════════════════════════════════════════════════════ */
function SceneCta() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = useScale();

  const sceneOp = lerp(frame, [0, 18], [0, 1]);
  const orbScale = spring({ frame, fps, config: { damping: 16, stiffness: 50 } });

  const headOp = lerp(frame, [18, 44], [0, 1]);
  const headY = lerp(frame, [18, 44], [16 * s, 0]);
  const subOp = lerp(frame, [36, 60], [0, 1]);
  const btnOp = lerp(frame, [54, 74], [0, 1]);
  const btnS = lerp(frame, [54, 74], [0.93, 1]);

  return (
    <AbsoluteFill style={{ background: C.bg, opacity: sceneOp, alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 44 * s }}>
      <Grain />
      <Grid opacity={0.25} />
      <div style={{
        position: "absolute", inset: 0,
        background: `radial-gradient(ellipse 62% 54% at 50% 50%, ${C.blue}14 0%, transparent 65%)`,
      }} />

      <div style={{ transform: `scale(${orbScale})`, zIndex: 1 }}>
        <SherpaOrbVideo size={210 * s} frame={frame} state="idle" glow={1.35} />
      </div>

      <div style={{ textAlign: "center", zIndex: 1 }}>
        <div style={{
          opacity: headOp, transform: `translateY(${headY}px)`,
          fontFamily: '"Geist", "Inter", -apple-system, sans-serif',
          fontSize: 84 * s, fontWeight: 600, color: C.fg,
          letterSpacing: -3.2 * s, lineHeight: 1.0,
        }}>
          Any repo. No setup.
        </div>
        <div style={{
          opacity: subOp,
          fontFamily: '"Geist", "Inter", -apple-system, sans-serif',
          fontSize: 27 * s, fontWeight: 400, color: C.dim,
          marginTop: 18 * s, letterSpacing: -0.4 * s,
        }}>
          No API key required. Free to start.
        </div>
        <div style={{
          opacity: btnOp, transform: `scale(${btnS})`,
          display: "inline-block", marginTop: 42 * s,
          background: C.white, color: "#000",
          borderRadius: 14 * s, padding: `${19 * s}px ${56 * s}px`,
          fontFamily: '"Geist", "Inter", -apple-system, sans-serif',
          fontSize: 23 * s, fontWeight: 600, letterSpacing: -0.3 * s,
        }}>
          Try Sherpa →
        </div>
      </div>
    </AbsoluteFill>
  );
}

/* ─── Main composition ───────────────────────────────────────── */
export const SherpaAd: React.FC = () => {
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      {/* 0–5s: Intro */}
      <Sequence from={0} durationInFrames={150}>
        <SceneIntro />
      </Sequence>
      {/* 5–10s: Problem */}
      <Sequence from={150} durationInFrames={150}>
        <SceneProblem />
      </Sequence>
      {/* 10–15s: Ask */}
      <Sequence from={300} durationInFrames={150}>
        <SceneAsk />
      </Sequence>
      {/* 15–23s: Answer */}
      <Sequence from={450} durationInFrames={240}>
        <SceneAnswer />
      </Sequence>
      {/* 23–27s: Features */}
      <Sequence from={690} durationInFrames={120}>
        <SceneFeatures />
      </Sequence>
      {/* 27–30s: CTA */}
      <Sequence from={810} durationInFrames={90}>
        <SceneCta />
      </Sequence>
    </AbsoluteFill>
  );
};
