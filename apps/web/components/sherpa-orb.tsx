"use client";

import { motion, useAnimation } from "framer-motion";
import { useEffect } from "react";
import { cn } from "../lib/utils";

type OrbState = "idle" | "thinking" | "responding";
type OrbSize = "xs" | "sm" | "md" | "lg" | "xl";

interface SherpaOrbProps {
  state?: OrbState;
  size?: OrbSize;
  className?: string;
}

const sizes: Record<OrbSize, { container: number; dotR: number; glowR: number; center: number }> = {
  xs: { container: 24, dotR: 1.8, glowR: 7, center: 12 },
  sm: { container: 36, dotR: 2.2, glowR: 11, center: 18 },
  md: { container: 56, dotR: 3, glowR: 17, center: 28 },
  lg: { container: 88, dotR: 4, glowR: 26, center: 44 },
  xl: { container: 140, dotR: 5.5, glowR: 40, center: 70 },
};

/* dot positions as fractions of the container size */
const DOT_FRACTIONS = [
  { x: 0.50, y: 0.50 }, // center — always lit
  { x: 0.50, y: 0.17 }, // top
  { x: 0.78, y: 0.28 }, // top-right
  { x: 0.83, y: 0.60 }, // right
  { x: 0.65, y: 0.83 }, // bottom-right
  { x: 0.35, y: 0.83 }, // bottom-left
  { x: 0.17, y: 0.60 }, // left
  { x: 0.22, y: 0.28 }, // top-left
];

const idleFloats = [
  [0, 0],
  [-2, -3],
  [2, -2],
  [3, 1],
  [1, 3],
  [-2, 2],
  [-3, -1],
  [1, -2],
];

export function SherpaOrb({ state = "idle", size = "md", className }: SherpaOrbProps) {
  const { container, dotR, glowR, center } = sizes[size];
  const controls = useAnimation();

  useEffect(() => {
    if (state === "thinking") {
      controls.start({
        rotate: 360,
        transition: { duration: 1.4, ease: "linear", repeat: Infinity },
      });
    } else {
      controls.start({ rotate: 0, transition: { duration: 0.5 } });
    }
  }, [state, controls]);

  const isThinking = state === "thinking";
  const isResponding = state === "responding";

  return (
    <div
      className={cn("relative shrink-0", className)}
      style={{ width: container, height: container }}
    >
      {/* ambient glow behind the orb */}
      <div
        className="absolute inset-0 rounded-full transition-opacity duration-700"
        style={{
          background: `radial-gradient(circle, hsl(var(--sherpa-glow)/0.18) 0%, transparent 72%)`,
          opacity: isThinking ? 1 : 0.6,
        }}
      />

      <svg
        width={container}
        height={container}
        viewBox={`0 0 ${container} ${container}`}
        overflow="visible"
      >
        <defs>
          <filter id={`glow-${size}`} x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation={dotR * 0.9} result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* rotating ring for thinking state */}
        {isThinking && (
          <motion.circle
            cx={center}
            cy={center}
            r={glowR * 0.85}
            fill="none"
            stroke={`hsl(var(--sherpa-glow)/0.25)`}
            strokeWidth="1"
            strokeDasharray="4 6"
            animate={{ rotate: 360 }}
            transition={{ duration: 2.5, ease: "linear", repeat: Infinity }}
            style={{ originX: `${center}px`, originY: `${center}px` }}
          />
        )}

        {/* dots */}
        <motion.g
          animate={controls}
          style={{ transformOrigin: `${center}px ${center}px` }}
        >
          {DOT_FRACTIONS.map((pos, i) => {
            const cx = pos.x * container;
            const cy = pos.y * container;
            const [dx, dy] = idleFloats[i];
            const isCenterDot = i === 0;

            return (
              <motion.circle
                key={i}
                cx={cx}
                cy={cy}
                r={isCenterDot ? dotR * 1.35 : dotR}
                fill={`hsl(var(--sherpa-dot))`}
                filter={`url(#glow-${size})`}
                opacity={isCenterDot ? 1 : i < 3 ? 0.9 : 0.65}
                animate={
                  isThinking
                    ? { opacity: [0.4, 1, 0.4], scale: [0.85, 1.15, 0.85] }
                    : isResponding
                    ? { scale: [1, 1.6, 1], opacity: [1, 0.6, 1] }
                    : {
                        x: [0, dx, 0, -dx / 2, 0],
                        y: [0, dy, 0, -dy / 2, 0],
                      }
                }
                transition={
                  isThinking
                    ? { duration: 1.0, delay: i * 0.12, ease: "easeInOut", repeat: Infinity }
                    : isResponding
                    ? { duration: 0.5, delay: i * 0.06, ease: [0.22, 1, 0.36, 1] }
                    : {
                        duration: 3.5 + i * 0.4,
                        delay: i * 0.5,
                        ease: "easeInOut",
                        repeat: Infinity,
                        repeatType: "reverse",
                      }
                }
              />
            );
          })}
        </motion.g>
      </svg>
    </div>
  );
}

/* small variant used in chat bubbles / header */
export function SherpaAvatar({ state = "idle", className }: { state?: OrbState; className?: string }) {
  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-center rounded-full",
        "bg-gradient-to-br from-secondary to-card border border-border shadow-orb-sm",
        className
      )}
      style={{ width: 32, height: 32 }}
    >
      <SherpaOrb state={state} size="xs" />
    </div>
  );
}

/* typing indicator — three bouncing dots */
export function TypingIndicator() {
  return (
    <div className="message-sherpa flex items-center gap-1 px-4 py-3">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="block h-1.5 w-1.5 rounded-full bg-muted-foreground"
          animate={{ y: [0, -4, 0] }}
          transition={{ duration: 0.9, delay: i * 0.18, ease: "easeInOut", repeat: Infinity }}
        />
      ))}
    </div>
  );
}
