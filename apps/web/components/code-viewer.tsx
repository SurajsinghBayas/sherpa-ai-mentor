"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Copy, FileCode2, X } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError } from "../lib/api";
import { langFor, langLabel } from "../lib/highlight";
import { cn } from "../lib/utils";
import { SourceLines } from "./source-code";

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
  const lang = langFor(path);
  const cut = path.lastIndexOf("/") + 1;
  const dir = path.slice(0, cut);
  const name = path.slice(cut);

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
        className="fixed inset-y-0 right-0 z-overlay flex w-full max-w-4xl flex-col border-l border-border bg-card shadow-pop"
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ duration: 0.32, ease: [0.32, 0.72, 0, 1] }}
      >
        <header className="flex items-center gap-3 border-b border-border px-4 py-3">
          <FileCode2 className="size-4 shrink-0 text-muted-foreground" />
          <div className="min-w-0 flex-1">
            <p className="truncate font-mono text-[13px]" title={path}>
              <span className="text-muted-foreground">{dir}</span>
              <span className="font-medium text-foreground">{name}</span>
            </p>
            <p className="mt-0.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <span className="rounded border border-border px-1 font-mono text-[10px] leading-4">{langLabel(lang)}</span>
              <span>
                Lines {target.start}–{target.end} cited
                {lines ? ` · ${lines.length} in file` : ""}
              </span>
            </p>
          </div>
          <button
            type="button"
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
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
            title="Close (Esc)"
            aria-label="Close"
          >
            <X className="size-4" />
          </button>
        </header>
        {error ? (
          <p className="flex-1 bg-editor px-4 py-3 text-sm text-destructive">{error}</p>
        ) : !lines ? (
          <div className="flex-1 space-y-2 bg-editor px-4 py-4" aria-label="Loading file">
            {[72, 54, 88, 40, 66, 58].map((w, i) => (
              <div key={i} className="h-3 rounded bg-editor-border/70" style={{ width: `${w}%` }} />
            ))}
          </div>
        ) : (
          <SourceLines
            code={lines.join("\n")}
            lang={lang}
            hit={{ start: target.start, end: target.end }}
            hitRef={firstRef}
            className="flex-1"
          />
        )}
      </motion.aside>
    </>
  );
}

/** A clickable `file:12-30` reference.
 *  - chip: standalone, in lists of sources
 *  - inline: inside a sentence, reads like a link rather than a badge
 *  - row: one line of a file list (name left, line range right) */
export function CitationChip({
  file,
  start,
  end,
  compact = false,
  variant = "chip",
  className,
}: {
  file: string;
  start: number;
  end: number;
  compact?: boolean;
  variant?: "chip" | "inline" | "row";
  className?: string;
}) {
  const { open } = useCodeViewer();
  const name = compact || variant !== "chip" ? file.split("/").slice(-1)[0] : file;
  const lines = `${start}${end !== start ? `–${end}` : ""}`;
  const props = { type: "button" as const, onClick: () => open(file, start, end), title: `Open ${file}, lines ${start}–${end}` };

  if (variant === "inline") {
    return (
      <button
        {...props}
        className={cn(
          "inline align-baseline font-mono text-[0.86em] text-primary underline decoration-primary/30 underline-offset-[3px]",
          "transition-colors hover:decoration-primary",
          className
        )}
      >
        {name}:{lines}
      </button>
    );
  }
  if (variant === "row") {
    return (
      <button
        {...props}
        className={cn(
          "flex w-full min-w-0 items-center gap-2 px-3 py-1.5 text-left font-mono text-xs transition-colors hover:bg-secondary",
          className
        )}
      >
        <FileCode2 className="size-3.5 shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate">{file}</span>
        <span className="shrink-0 tabular-nums text-muted-foreground">{lines}</span>
      </button>
    );
  }
  return (
    <button
      {...props}
      className={cn(
        "inline-flex max-w-full items-center gap-1 rounded-md border border-border bg-secondary/60 px-1.5 py-px",
        "align-baseline font-mono text-[11px] leading-5 text-foreground/80",
        "transition-colors hover:border-primary/40 hover:text-primary",
        className
      )}
    >
      <FileCode2 className="size-3 shrink-0 text-muted-foreground" />
      <span className="truncate">
        {name}:{lines}
      </span>
    </button>
  );
}
