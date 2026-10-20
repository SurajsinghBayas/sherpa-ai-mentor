"use client";

import { forwardRef } from "react";
import type { ThemedToken } from "shiki/core";
import { useTokens } from "../lib/highlight";
import { cn } from "../lib/utils";

/** Line-numbered, syntax-highlighted source on the theme's editor surface.
 *  Renders plain text first and swaps in colours once shiki has tokenized, so nothing waits on it. */
export function SourceLines({
  code,
  lang,
  start = 1,
  hit,
  hitRef,
  className,
}: {
  code: string;
  lang: string | null;
  /** number of the first line */
  start?: number;
  /** cited range, in file line numbers */
  hit?: { start: number; end: number };
  /** attached to the first cited line, for scrolling it into view */
  hitRef?: React.Ref<HTMLDivElement>;
  className?: string;
}) {
  const tokens = useTokens(code, lang);
  const lines = code.split("\n");
  const width = String(start + lines.length - 1).length;

  return (
    <div
      className={cn(
        "scroll-thin overflow-auto bg-editor py-3 font-mono text-[12.5px] leading-[1.7] text-editor-foreground [tab-size:4]",
        className
      )}
    >
      {lines.map((ln, i) => {
        const n = start + i;
        const isHit = !!hit && n >= hit.start && n <= hit.end;
        return (
          <Line key={n} ref={isHit && n === hit!.start ? hitRef : undefined} n={n} width={width} hit={isHit}>
            {tokens?.[i] ? <Tokens line={tokens[i]} /> : ln}
          </Line>
        );
      })}
    </div>
  );
}

const Line = forwardRef<HTMLDivElement, { n: number; width: number; hit: boolean; children: React.ReactNode }>(
  function Line({ n, width, hit, children }, ref) {
    return (
      <div ref={ref} className={cn("flex min-w-max", hit && "bg-editor-hit")}>
        <span
          aria-hidden
          style={{ width: `calc(${width}ch + 2.25rem)` }}
          className={cn(
            "sticky left-0 shrink-0 select-none border-r border-editor-border pr-3 text-right tabular-nums",
            hit
              ? "bg-editor-hit text-primary shadow-[inset_2px_0_0_hsl(var(--primary))]"
              : "bg-editor text-editor-gutter"
          )}
        >
          {n}
        </span>
        <span className="whitespace-pre pl-4 pr-6">{children || " "}</span>
      </div>
    );
  }
);

function Tokens({ line }: { line: ThemedToken[] }) {
  if (!line.length) return null;
  return (
    <>
      {line.map((t, j) => (
        <span key={j} className="shiki-t" style={t.htmlStyle as React.CSSProperties}>
          {t.content}
        </span>
      ))}
    </>
  );
}

/** A fenced block without line numbers (answers, chat), on the same surface. */
export function CodeSnippet({ code, lang, className }: { code: string; lang: string | null; className?: string }) {
  const tokens = useTokens(code, lang);
  const lines = code.replace(/\n$/, "").split("\n");
  return (
    <pre
      className={cn(
        "scroll-thin overflow-x-auto rounded-lg border border-editor-border bg-editor px-3.5 py-3 font-mono text-[12.5px] leading-[1.65] text-editor-foreground [tab-size:4]",
        className
      )}
    >
      {lines.map((ln, i) => (
        <div key={i} className="min-w-max whitespace-pre">
          {tokens?.[i] ? <Tokens line={tokens[i]} /> : ln || " "}
        </div>
      ))}
    </pre>
  );
}
