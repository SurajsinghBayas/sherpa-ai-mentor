import React from "react";
import {
  AbsoluteFill,
  interpolate,
  interpolateColors,
  Sequence,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

/* ── Easing ── */
const EASE_OUT_EXPO = (t: number) => (t === 1 ? 1 : 1 - Math.pow(2, -10 * t));

/* ── Design tokens ── */
const BG = "#0c0c0c";
const CARD_BG = "#141414";
const BORDER = "#1f1f1f";
const FG = "#f0f0f0";
const MUTED = "#666";
const BLUE = "#4a9eff";

/* ── Dot positions (normalized 0-1) ── */
const DOT_POSITIONS = [
  { x: 0.5, y: 0.5 },
  { x: 0.5, y: 0.18 },
  { x: 0.78, y: 0.3 },
  { x: 0.82, y: 0.62 },
  { x: 0.62, y: 0.82 },
  { x: 0.38, y: 0.82 },
  { x: 0.18, y: 0.62 },
  { x: 0.22, y: 0.3 },
];

/* ── SherpaOrbVideo — standalone SVG orb for Remotion ── */
function SherpaOrbVideo({
  size,
  frame,
  state = "idle",
}: {
  size: number;
  frame: number;
  state?: "idle" | "thinking";
}) {
  const center = size / 2;
  const dotR = size * 0.052;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <defs>
        <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation={dotR * 0.85} result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <radialGradient id="orb-bg" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor={BLUE} stopOpacity="0.12" />
          <stop offset="100%" stopColor={BLUE} stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle cx={center} cy={center} r={center * 0.9} fill="url(#orb-bg)" />
      {DOT_POSITIONS.map((pos, i) => {
        const cx = pos.x * size;
        const cy = pos.y * size;
        const phase = (frame / 80 + i * 0.7) * Math.PI * 2;
        const dx = state === "idle" ? Math.sin(phase) * (size * 0.018) : 0;
        const dy = state === "idle" ? Math.cos(phase * 1.3) * (size * 0.018) : 0;
        const rotAngle = state === "thinking" ? (frame / 40) * Math.PI * 2 : 0;
        const rx = cx - center;
        const ry = cy - center;
        const rotCx = center + rx * Math.cos(rotAngle) - ry * Math.sin(rotAngle);
        const rotCy = center + rx * Math.sin(rotAngle) + ry * Math.cos(rotAngle);
        const finalCx = state === "thinking" ? rotCx : cx + dx;
        const finalCy = state === "thinking" ? rotCy : cy + dy;
        return (
          <circle
            key={i}
            cx={finalCx}
            cy={finalCy}
            r={i === 0 ? dotR * 1.35 : dotR}
            fill={BLUE}
            opacity={i === 0 ? 1 : i < 3 ? 0.88 : 0.55}
            filter="url(#glow)"
          />
        );
      })}
    </svg>
  );
}

/* ── Scene 1: Intro (0–5s, frames 0–150) ── */
function SceneIntro({ frame }: { frame: number }) {
  const { fps } = useVideoConfig();
  const orbScale = spring({ frame, fps, config: { damping: 16, stiffness: 60 } });
  const textOpacity = interpolate(frame, [40, 80], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const textY = interpolate(frame, [40, 80], [20, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ background: BG, alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 40 }}>
      {/* Grid */}
      <div style={{
        position: "absolute", inset: 0,
        backgroundImage: `linear-gradient(${BORDER} 1px, transparent 1px), linear-gradient(90deg, ${BORDER} 1px, transparent 1px)`,
        backgroundSize: "80px 80px",
        opacity: 0.4,
      }} />
      {/* Radial glow */}
      <div style={{
        position: "absolute", inset: 0,
        background: `radial-gradient(ellipse 50% 40% at 50% 50%, ${BLUE}14 0%, transparent 70%)`,
      }} />

      <div style={{ transform: `scale(${orbScale})`, position: "relative", zIndex: 1 }}>
        <SherpaOrbVideo size={180} frame={frame} state="idle" />
      </div>

      <div style={{ opacity: textOpacity, transform: `translateY(${textY}px)`, textAlign: "center", position: "relative", zIndex: 1 }}>
        <div style={{ fontFamily: "Geist, sans-serif", fontSize: 72, fontWeight: 600, color: FG, letterSpacing: -2, lineHeight: 1.05 }}>
          Meet Sherpa.
        </div>
        <div style={{ fontFamily: "Geist, sans-serif", fontSize: 28, color: MUTED, marginTop: 16, fontWeight: 400 }}>
          Your AI guide through any codebase.
        </div>
      </div>
    </AbsoluteFill>
  );
}

/* ── Scene 2: Problem (5–12s, frames 150–360) ── */
function SceneProblem({ frame }: { frame: number }) {
  const localFrame = frame;
  const opacity = interpolate(localFrame, [0, 30], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const lines = [
    "app/auth/middleware.py",
    "services/user/repository.py",
    "core/events/dispatcher.py",
    "utils/crypto/jwt_handler.py",
    "api/v2/endpoints/auth.py",
    "models/domain/user.py",
    "infrastructure/cache/redis.py",
  ];

  return (
    <AbsoluteFill style={{ background: BG, opacity }}>
      {/* Left: confused dev */}
      <div style={{
        position: "absolute", left: 0, top: 0, width: "45%", height: "100%",
        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: 80, gap: 24,
      }}>
        <div style={{ fontFamily: "Geist, sans-serif", fontSize: 42, fontWeight: 600, color: FG, lineHeight: 1.2, textAlign: "center" }}>
          New to a codebase?
        </div>
        <div style={{ fontFamily: "Geist, sans-serif", fontSize: 22, color: MUTED, textAlign: "center", lineHeight: 1.6 }}>
          Weeks of reading. Endless questions. No clear starting point.
        </div>
        <div style={{ fontSize: 80, marginTop: 16 }}>😵</div>
      </div>

      {/* Right: overwhelming file tree */}
      <div style={{
        position: "absolute", right: 80, top: "50%", transform: "translateY(-50%)",
        background: CARD_BG, border: `1px solid ${BORDER}`, borderRadius: 16, padding: "24px 32px",
        fontFamily: "Geist Mono, monospace", fontSize: 16, color: MUTED, lineHeight: 2,
        width: 420,
      }}>
        <div style={{ color: "#444", marginBottom: 8, fontSize: 13 }}>📁 src/</div>
        {lines.map((l, i) => {
          const lineOpacity = interpolate(
            localFrame,
            [20 + i * 12, 50 + i * 12],
            [0, 1],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
          );
          return (
            <div key={l} style={{ opacity: lineOpacity, paddingLeft: 16 }}>
              📄 {l}
            </div>
          );
        })}
        <div style={{ color: "#333", marginTop: 8 }}>... +247 more files</div>
      </div>
    </AbsoluteFill>
  );
}

/* ── Scene 3: Solution (12–22s, frames 360–660) ── */
function SceneSolution({ frame }: { frame: number }) {
  const localFrame = frame;
  const opacity = interpolate(localFrame, [0, 20], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const messages = [
    { role: "user", text: "How does user authentication work?", frame: 20 },
    {
      role: "sherpa",
      text: "Auth flows through POST /api/auth/login. The handler validates\ncredentials with bcrypt, then issues a 24h JWT.",
      sources: ["app/auth.py:38-44", "app/security.py:22-33"],
      frame: 70,
    },
    { role: "user", text: "Where is the database schema defined?", frame: 140 },
    {
      role: "sherpa",
      text: "The User model is in app/models/user.py:12-34.\nPostgres in production, SQLite for local dev.",
      sources: ["app/models/user.py:12-34"],
      frame: 180,
    },
  ];

  return (
    <AbsoluteFill style={{ background: BG, opacity }}>
      {/* Left panel: Sherpa */}
      <div style={{
        position: "absolute", left: 80, top: "50%", transform: "translateY(-50%)",
        display: "flex", flexDirection: "column", alignItems: "center", gap: 16,
      }}>
        <SherpaOrbVideo size={140} frame={localFrame} state={localFrame > 50 && localFrame < 100 ? "thinking" : "idle"} />
        <div style={{ fontFamily: "Geist, sans-serif", fontSize: 20, fontWeight: 600, color: FG }}>Sherpa</div>
        <div style={{ fontFamily: "Geist, sans-serif", fontSize: 14, color: MUTED }}>AI Codebase Guide</div>
      </div>

      {/* Chat window */}
      <div style={{
        position: "absolute", right: 80, top: "50%", transform: "translateY(-50%)",
        background: CARD_BG, border: `1px solid ${BORDER}`, borderRadius: 20,
        width: 700, overflow: "hidden",
      }}>
        {/* Chrome */}
        <div style={{
          background: "#0f0f0f", borderBottom: `1px solid ${BORDER}`,
          padding: "14px 20px", display: "flex", alignItems: "center", gap: 8,
        }}>
          <div style={{ width: 10, height: 10, borderRadius: "50%", background: BORDER }} />
          <div style={{ width: 10, height: 10, borderRadius: "50%", background: BORDER }} />
          <div style={{ width: 10, height: 10, borderRadius: "50%", background: BORDER }} />
          <span style={{ marginLeft: 12, fontFamily: "Geist Mono, monospace", fontSize: 12, color: MUTED }}>
            gothinkster/realworld
          </span>
        </div>

        {/* Messages */}
        <div style={{ padding: "24px 20px", minHeight: 380, display: "flex", flexDirection: "column", gap: 16 }}>
          {messages.map((msg, i) => {
            const msgOpacity = interpolate(
              localFrame,
              [msg.frame, msg.frame + 25],
              [0, 1],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
            );
            const msgY = interpolate(
              localFrame,
              [msg.frame, msg.frame + 25],
              [10, 0],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
            );

            return (
              <div
                key={i}
                style={{
                  opacity: msgOpacity,
                  transform: `translateY(${msgY}px)`,
                  display: "flex",
                  justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
                }}
              >
                {msg.role === "user" ? (
                  <div style={{
                    background: "#fff", color: "#000", borderRadius: "16px 16px 4px 16px",
                    padding: "12px 18px", fontFamily: "Geist, sans-serif", fontSize: 15, maxWidth: "70%",
                  }}>
                    {msg.text}
                  </div>
                ) : (
                  <div style={{ maxWidth: "85%" }}>
                    <div style={{
                      background: "#1a1a1a", color: FG, borderRadius: "16px 16px 16px 4px",
                      border: `1px solid ${BORDER}`, padding: "12px 18px",
                      fontFamily: "Geist, sans-serif", fontSize: 15, lineHeight: 1.6,
                    }}>
                      {msg.text}
                    </div>
                    {(msg as any).sources && (
                      <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                        {(msg as any).sources.map((s: string) => (
                          <div key={s} style={{
                            background: "#111", border: `1px solid ${BORDER}`,
                            borderRadius: 8, padding: "4px 10px",
                            fontFamily: "Geist Mono, monospace", fontSize: 11, color: MUTED,
                          }}>
                            📄 {s}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
}

/* ── Scene 4: Features (22–27s, frames 660–810) ── */
function SceneFeatures({ frame }: { frame: number }) {
  const localFrame = frame;
  const opacity = interpolate(localFrame, [0, 20], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  const features = [
    { icon: "💬", title: "Grounded Q&A", desc: "Answers cite exact file:line" },
    { icon: "🗺️", title: "Architecture maps", desc: "Mermaid component diagrams" },
    { icon: "🧭", title: "Guided tours", desc: "Trace any feature end-to-end" },
    { icon: "✅", title: "Starter tasks", desc: "First PRs from the real repo" },
    { icon: "🔑", title: "Bring your keys", desc: "OpenAI, Anthropic, Gemini" },
    { icon: "🛡️", title: "Citation verifier", desc: "No hallucinations, ever" },
  ];

  return (
    <AbsoluteFill style={{ background: BG, opacity, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 48 }}>
      <div style={{
        fontFamily: "Geist, sans-serif", fontSize: 52, fontWeight: 600, color: FG,
        letterSpacing: -1.5, textAlign: "center",
      }}>
        Everything you need to understand any codebase.
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, width: 1100 }}>
        {features.map((f, i) => {
          const cardOpacity = interpolate(
            localFrame,
            [20 + i * 18, 50 + i * 18],
            [0, 1],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
          );
          const cardY = interpolate(
            localFrame,
            [20 + i * 18, 50 + i * 18],
            [16, 0],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" }
          );
          return (
            <div
              key={f.title}
              style={{
                opacity: cardOpacity,
                transform: `translateY(${cardY}px)`,
                background: CARD_BG,
                border: `1px solid ${BORDER}`,
                borderRadius: 16,
                padding: "24px 28px",
              }}
            >
              <div style={{ fontSize: 36, marginBottom: 12 }}>{f.icon}</div>
              <div style={{ fontFamily: "Geist, sans-serif", fontSize: 18, fontWeight: 600, color: FG }}>{f.title}</div>
              <div style={{ fontFamily: "Geist, sans-serif", fontSize: 14, color: MUTED, marginTop: 6 }}>{f.desc}</div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
}

/* ── Scene 5: CTA (27–30s, frames 810–900) ── */
function SceneCta({ frame }: { frame: number }) {
  const { fps } = useVideoConfig();
  const localFrame = frame;
  const orbScale = spring({ frame: localFrame, fps, config: { damping: 14, stiffness: 55 } });
  const textOpacity = interpolate(localFrame, [20, 50], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });

  return (
    <AbsoluteFill style={{ background: BG, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 40 }}>
      <div style={{
        position: "absolute", inset: 0,
        background: `radial-gradient(ellipse 60% 50% at 50% 50%, ${BLUE}10 0%, transparent 70%)`,
      }} />

      <div style={{ transform: `scale(${orbScale})`, position: "relative", zIndex: 1 }}>
        <SherpaOrbVideo size={160} frame={localFrame} state="idle" />
      </div>

      <div style={{ opacity: textOpacity, textAlign: "center", position: "relative", zIndex: 1 }}>
        <div style={{
          fontFamily: "Geist, sans-serif", fontSize: 72, fontWeight: 600, color: FG,
          letterSpacing: -2, lineHeight: 1.05,
        }}>
          Start with any repo.
        </div>
        <div style={{
          fontFamily: "Geist, sans-serif", fontSize: 28, color: MUTED, marginTop: 16,
        }}>
          No setup. No API key required. Free.
        </div>
        <div style={{
          marginTop: 36, background: FG, color: "#000", borderRadius: 12,
          padding: "18px 48px", fontFamily: "Geist, sans-serif", fontSize: 22, fontWeight: 600,
          display: "inline-block",
        }}>
          Try Sherpa →
        </div>
      </div>
    </AbsoluteFill>
  );
}

/* ── Main composition ── */
export const SherpaAd: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill style={{ background: BG, fontFamily: "Geist, sans-serif" }}>
      {/* Scene 1: Intro (0–150) */}
      <Sequence from={0} durationInFrames={150}>
        <SceneIntro frame={frame} />
      </Sequence>

      {/* Scene 2: Problem (150–360) */}
      <Sequence from={150} durationInFrames={210}>
        <SceneProblem frame={frame - 150} />
      </Sequence>

      {/* Scene 3: Solution (360–660) */}
      <Sequence from={360} durationInFrames={300}>
        <SceneSolution frame={frame - 360} />
      </Sequence>

      {/* Scene 4: Features (660–810) */}
      <Sequence from={660} durationInFrames={150}>
        <SceneFeatures frame={frame - 660} />
      </Sequence>

      {/* Scene 5: CTA (810–900) */}
      <Sequence from={810} durationInFrames={90}>
        <SceneCta frame={frame - 810} />
      </Sequence>
    </AbsoluteFill>
  );
};
