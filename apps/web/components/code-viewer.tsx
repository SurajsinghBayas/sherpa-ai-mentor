"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Copy, FileCode2, X } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "../lib/api";
import { cn } from "../lib/utils";

type Target = { file: string; start: number; end: number };

const Ctx = createContext<{ repoId: string; open: (file: string, start: number, end: number) => void }>({
  repoId: "",
  open: () => {},
});

export const useCodeViewer = () => useContext(Ctx);

/** Wraps the workspace; any citation chip inside can open the exact lines it cites. */
export function CodeViewerProvider({ repoId, children }: { repoId: string; children: React.ReactNode }) {
  const [target, setTarget] = useState<Target | null>(null);
  const open = useCallback((file: string, start: number, end: number) => setTarget({ file, start, end }), []);
  return (
    <Ctx.Provider value={{ repoId, open }}>
      {children}
      <AnimatePresence>
        {target && repoId && <CodeDrawer repoId={repoId} target={target} onClose={() => setTarget(null)} />}
      </AnimatePresence>
    </Ctx.Provider>
  );
}

function CodeDrawer({ repoId, target, onClose }: { repoId: string; target: Target; onClose: () => void }) {
  const [lines, setLines] = useState<string[] | null>(null);
  const [path, setPath] = useState(target.file);
  const [error, setError] = useState("");
  const firstRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLines(null);
    setError("");
    api
      .file(repoId, target.file)
      .then((f) => {
        setLines(f.lines);
        setPath(f.path);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : "Could not load file"));
  }, [repoId, target.file]);

  useEffect(() => {
    if (lines) firstRef.current?.scrollIntoView({ block: "center" });
  }, [lines, target.start]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const cited = lines ? lines.slice(target.start - 1, target.end).join("\n") : "";

  return (
    <>
      <motion.div
        className="fixed inset-0 z-overlay bg-navy-deep/40"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      />
      <motion.aside
        role="dialog"
        aria-label={`Source: ${path}`}
        className="fixed inset-y-0 right-0 z-overlay flex w-full max-w-3xl flex-col border-l border-border bg-card shadow-pop"
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ duration: 0.32, ease: [0.32, 0.72, 0, 1] }}
      >
        <header className="flex items-center gap-3 border-b border-border px-4 py-3">
          <FileCode2 className="size-4 shrink-0 text-muted-foreground" />
          <div className="min-w-0 flex-1">
            <p className="truncate font-mono text-sm">{path}</p>
            <p className="text-[11px] text-muted-foreground">
              Cited lines {target.start}–{target.end}
              {lines ? ` · ${lines.length} lines in file` : ""}
            </p>
          </div>
          <button
            onClick={() => {
              navigator.clipboard.writeText(cited).then(() => toast.success("Cited lines copied"));
            }}
            disabled={!lines}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground disabled:opacity-40"
            title="Copy cited lines"
            aria-label="Copy cited lines"
          >
            <Copy className="size-4" />
          </button>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
            title="Close (Esc)"
            aria-label="Close"
          >
            <X className="size-4" />
          </button>
        </header>
        <div className="scroll-thin-code flex-1 overflow-auto bg-code py-3 font-mono text-[12px] leading-[1.6] text-code-foreground">
          {error && <p className="px-4 text-sm text-destructive">{error}</p>}
          {!lines && !error && <p className="px-4 text-sm text-muted-foreground">Loading…</p>}
          {lines?.map((ln, i) => {
            const n = i + 1;
            const hit = n >= target.start && n <= target.end;
            return (
              <div
                key={n}
                ref={n === target.start ? firstRef : undefined}
                className={cn("flex min-w-max pr-4", hit && "bg-code-line/15")}
              >
                <span
                  className={cn(
                    "sticky left-0 w-14 shrink-0 select-none pr-3 text-right",
                    hit ? "bg-[hsl(var(--code))] text-sky-brand shadow-[inset_2px_0_0_hsl(var(--code-line))]" : "bg-code text-code-muted"
                  )}
                >
                  {n}
                </span>
                <span className={cn("whitespace-pre pl-3", hit ? "text-code-foreground" : "text-code-foreground/70")}>
                  {ln || " "}
                </span>
              </div>
            );
          })}
        </div>
      </motion.aside>
    </>
  );
}

/** A clickable `file:12-30` chip. */
export function CitationChip({
  file,
  start,
  end,
  compact = false,
  className,
}: {
  file: string;
  start: number;
  end: number;
  compact?: boolean;
  className?: string;
}) {
  const { open } = useCodeViewer();
  const name = compact ? file.split("/").slice(-1)[0] : file;
  return (
    <button
      type="button"
      onClick={() => open(file, start, end)}
      title={`Open ${file} lines ${start}-${end}`}
      className={cn(
        "mx-0.5 inline-flex max-w-full items-center gap-1 rounded-md border border-primary/25 bg-primary/[0.07]",
        "px-1.5 py-px align-baseline font-mono text-[11px] leading-5 text-primary",
        "transition-colors hover:border-primary/50 hover:bg-primary/15",
        className
      )}
    >
      <FileCode2 className="size-3 shrink-0" />
      <span className="truncate">
        {name}:{start}
        {end !== start ? `-${end}` : ""}
      </span>
    </button>
  );
}
