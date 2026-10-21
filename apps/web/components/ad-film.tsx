"use client";

import { useRef, useState } from "react";
import { Play } from "lucide-react";
import { cn } from "../lib/utils";

// The 30s landing film: a poster with one play button; native controls appear once it plays.
export function AdFilm({ className }: { className?: string }) {
  const ref = useRef<HTMLVideoElement>(null);
  const [started, setStarted] = useState(false);

  function start() {
    setStarted(true);
    ref.current?.play().catch(() => {});
  }

  return (
    <div
      className={cn(
        "group relative aspect-video overflow-hidden rounded-2xl border border-border bg-navy shadow-pop",
        className,
      )}
    >
      <video
        ref={ref}
        className="size-full object-cover"
        src="/ads/sherpa-ad3-horizontal.mp4"
        poster="/ads/sherpa-ad3-horizontal.jpg"
        aria-label="Sherpa AI: a new joiner's first day, 30 second film"
        controls={started}
        playsInline
        preload="none"
      />
      {!started && (
        <button
          type="button"
          onClick={start}
          aria-label="Play the 30 second film"
          className="absolute inset-0 focus-visible:outline-none"
        >
          {/* sits under the poster's headline, in the copy column (left 6.25%, like the film's own margin) */}
          <span className="absolute left-[6.25%] top-[72%] flex items-center gap-2 rounded-full bg-navy p-1 pr-3 text-cream shadow-pop ring-1 ring-cream/10 transition-transform duration-200 group-hover:scale-105 group-focus-within:ring-2 group-focus-within:ring-sky-brand sm:gap-3 sm:py-2 sm:pl-2 sm:pr-5">
            <span className="grid size-7 place-items-center rounded-full bg-cream text-navy sm:size-9">
              <Play className="size-3 translate-x-px fill-current sm:size-4" />
            </span>
            <span className="text-xs font-medium sm:text-sm">Watch the film</span>
            <span className="font-mono text-[11px] text-cream/60 sm:text-xs">0:30</span>
          </span>
        </button>
      )}
    </div>
  );
}
