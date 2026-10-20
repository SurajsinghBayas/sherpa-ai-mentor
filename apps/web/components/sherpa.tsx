import { cn } from "../lib/utils";

/** Sherpa, the guide character from the style guide. Each pose matches what the app is doing. */
export type Pose =
  | "happy" // idle, greeting
  | "thinking" // waiting on the model
  | "coding" // tasks, CLI
  | "exploring" // tours, unfamiliar paths
  | "analyzing" // architecture, reviewing files
  | "explaining" // answers, docs
  | "success" // indexed, done
  | "guide" // onboarding, empty states
  | "walking" // long-running work (indexing)
  | "excited"; // celebrations

/* walking/excited exist only as animations; their still frame borrows the closest pose */
const STILL: Record<Pose, string> = {
  happy: "happy",
  thinking: "thinking",
  coding: "coding",
  exploring: "exploring",
  analyzing: "analyzing",
  explaining: "explaining",
  success: "success",
  guide: "guide",
  walking: "guide",
  excited: "success",
};

const LABEL: Record<Pose, string> = {
  happy: "Sherpa waving",
  thinking: "Sherpa thinking",
  coding: "Sherpa coding",
  exploring: "Sherpa reading a map",
  analyzing: "Sherpa inspecting with a magnifier",
  explaining: "Sherpa explaining",
  success: "Sherpa celebrating",
  guide: "Sherpa with a walking stick",
  walking: "Sherpa walking",
  excited: "Sherpa excited",
};

/**
 * The full-body character. Animated poses are GIFs; people who prefer reduced motion get the still
 * SVG through <picture>, so no JavaScript or hydration is involved. Sizes that are multiples of 16 keep
 * the pixel grid crisp.
 */
export function Sherpa({
  pose = "happy",
  size = 64,
  animated = true,
  decorative = false,
  className,
}: {
  pose?: Pose;
  size?: number;
  animated?: boolean;
  /** true when nearby text already says what Sherpa is doing */
  decorative?: boolean;
  className?: string;
}) {
  const still = `/mascot/${STILL[pose]}.svg`;
  const alt = decorative ? "" : LABEL[pose];
  if (!animated) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img src={still} alt={alt} width={size} height={size} draggable={false} className={cn("pixelated shrink-0 select-none", className)} />
    );
  }
  return (
    <picture className={cn("inline-block shrink-0 select-none", className)} style={{ width: size, height: size }}>
      <source media="(prefers-reduced-motion: reduce)" srcSet={still} />
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={`/mascot/${pose}.gif`} alt={alt} width={size} height={size} draggable={false} className="pixelated size-full" />
    </picture>
  );
}

/** Sherpa's head: the logo mark and the chat avatar. */
export function SherpaMark({ size = 24, className }: { size?: number; className?: string }) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src="/mascot/head.svg"
      alt=""
      width={size}
      height={Math.round((size * 30) / 36)}
      draggable={false}
      className={cn("pixelated shrink-0 select-none", className)}
    />
  );
}

/** Head in a tile: the avatar beside Sherpa's chat messages. */
export function SherpaAvatar({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn("flex size-8 shrink-0 items-center justify-center rounded-lg border border-border bg-cream", className)}
    >
      <SherpaMark size={22} />
    </span>
  );
}

/** The wordmark from the logo sheet: head + "Sherpa AI", with "AI" in Sherpa blue. */
export function Wordmark({ className, size = 26 }: { className?: string; size?: number }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-semibold", className)}>
      <SherpaMark size={size} />
      <span className="text-[15px] leading-none">
        Sherpa <span className="text-primary">AI</span>
      </span>
    </span>
  );
}

/** Sherpa with a speech bubble: the "in context" pattern from the style guide. */
export function SherpaSays({
  pose = "happy",
  size = 64,
  children,
  className,
}: {
  pose?: Pose;
  size?: number;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-start gap-3", className)}>
      <Sherpa pose={pose} size={size} decorative />
      <div className="bubble bubble-left mt-2 min-w-0 flex-1">{children}</div>
    </div>
  );
}
