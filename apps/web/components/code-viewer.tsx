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
        className="fixed inset-0 z-[60] bg-black/50 backdrop-blur-[2px]"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      />
      <motion.aside
        role="dialog"
        aria-label={`Source: ${path}`}
        className="fixed inset-y-0 right-0 z-[61] flex w-full max-w-3xl flex-col border-l border-border bg-card shadow-2xl"
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", damping: 30, stiffness: 300 }}
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
          >
            <Copy className="size-4" />
          </button>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
            title="Close (Esc)"
          >
            <X className="size-4" />
          </button>
        </header>
        <div className="code-scroll flex-1 overflow-auto bg-black/40 py-3 font-mono text-[12px] leading-[1.6]">
          {error && <p className="px-4 text-sm text-destructive">{error}</p>}
          {!lines && !error && <p className="px-4 text-sm text-muted-foreground">Loading…</p>}
          {lines?.map((ln, i) => {
            const n = i + 1;
            const hit = n >= target.start && n <= target.end;
            return (
              <div
                key={n}
                ref={n === target.start ? firstRef : undefined}
                className={cn("flex min-w-max pr-4", hit && "bg-sky-500/15")}
              >
                <span
                  className={cn(
                    "sticky left-0 w-14 shrink-0 select-none pr-3 text-right",
                    hit ? "bg-sky-950/80 text-sky-300" : "bg-[#0d0d0d] text-zinc-600"
                  )}
                >
                  {n}
                </span>
                <span className={cn("whitespace-pre pl-3", hit ? "text-zinc-100" : "text-zinc-400")}>
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
        "mx-0.5 inline-flex max-w-full items-center gap-1 rounded-md border border-sky-500/25 bg-sky-500/10",
        "px-1.5 py-px align-baseline font-mono text-[11px] leading-5 text-sky-700 dark:text-sky-300",
        "transition-colors hover:border-sky-500/50 hover:bg-sky-500/20",
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
