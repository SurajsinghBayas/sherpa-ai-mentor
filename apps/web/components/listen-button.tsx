"use client";

import { Square, Volume2 } from "lucide-react";
import { say, stop, useSpeaking } from "../lib/voice";
import { cn } from "../lib/utils";

/** Read `text` aloud; press again to stop. */
export function ListenButton({ id, text, className }: { id: string; text: string; className?: string }) {
  const { id: speaking } = useSpeaking();
  const on = speaking === id;
  return (
    <button
      type="button"
      onClick={() => (on ? stop() : say(id, text).catch(() => {}))}
      aria-pressed={on}
      className={cn(
        "inline-flex items-center gap-1 text-[11px] transition-colors",
        on ? "text-primary" : "text-muted-foreground hover:text-foreground",
        className
      )}
    >
      {on ? <Square className="size-3 fill-current" /> : <Volume2 className="size-3.5" />}
      {on ? "Stop" : "Listen"}
    </button>
  );
}
