"use client";

import ReactMarkdown, { defaultUrlTransform, type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { CitationChip } from "./code-viewer";
import { cn } from "../lib/utils";

// [path/to/file.py:12-30] → a markdown link with a cite: href, rendered as a chip.
const CITE = /\[([^\[\]\s:]+?):L?(\d+)(?:\s*[-–]\s*L?(\d+))?\](?!\()/g;

function linkCitations(md: string): string {
  // leave fenced code blocks untouched
  return md
    .split(/(```[\s\S]*?```)/g)
    .map((part, i) =>
      i % 2 === 1
        ? part
        : part.replace(CITE, (_m, file: string, a: string, b?: string) => {
            const end = b ?? a;
            return `[${file}:${a}-${end}](cite:${encodeURIComponent(file)}:${a}:${end})`;
          })
    )
    .join("");
}

const components: Components = {
  a({ href, children }) {
    if (href?.startsWith("cite:")) {
      const [, file, a, b] = href.match(/^cite:(.+):(\d+):(\d+)$/) || [];
      if (file) return <CitationChip file={decodeURIComponent(file)} start={+a} end={+b} compact />;
    }
    return (
      <a href={href} target="_blank" rel="noreferrer" className="font-medium text-primary underline-offset-2 hover:underline">
        {children}
      </a>
    );
  },
  p: ({ children }) => <p className="my-2 leading-relaxed first:mt-0 last:mb-0">{children}</p>,
  h1: ({ children }) => <h3 className="mb-2 mt-4 text-base font-semibold first:mt-0">{children}</h3>,
  h2: ({ children }) => <h3 className="mb-2 mt-4 text-[15px] font-semibold first:mt-0">{children}</h3>,
  h3: ({ children }) => <h4 className="mb-1.5 mt-3 text-sm font-semibold first:mt-0">{children}</h4>,
  h4: ({ children }) => <h5 className="mb-1 mt-3 text-sm font-medium first:mt-0">{children}</h5>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1.5 pl-5 marker:text-muted-foreground">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1.5 pl-5 marker:text-muted-foreground">{children}</ol>,
  li: ({ children }) => <li className="pl-1 leading-relaxed">{children}</li>,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
  blockquote: ({ children }) => (
    <blockquote className="my-3 border-l-2 border-tan bg-tan/10 py-1 pl-3 text-muted-foreground">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-4 border-border" />,
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-left text-xs">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border-b border-border bg-secondary/60 px-3 py-2 font-medium">{children}</th>,
  td: ({ children }) => <td className="border-b border-border/60 px-3 py-2 align-top">{children}</td>,
  pre: ({ children }) => (
    <pre className="scroll-thin-code my-3 overflow-x-auto rounded-lg bg-code p-3 font-mono text-[12px] leading-relaxed text-code-foreground">
      {children}
    </pre>
  ),
  code({ className, children }) {
    const block = /language-/.test(className || "") || String(children).includes("\n");
    if (block) return <code className={className}>{children}</code>;
    return (
      <code className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[0.85em] text-foreground">{children}</code>
    );
  },
};

export function Markdown({ text, className }: { text: string; className?: string }) {
  return (
    <div className={cn("text-sm text-card-foreground [overflow-wrap:anywhere]", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={components}
        // keep our cite: links; everything else goes through the safe default (no javascript: etc.)
        urlTransform={(url) => (url.startsWith("cite:") ? url : defaultUrlTransform(url))}
      >
        {linkCitations(text)}
      </ReactMarkdown>
    </div>
  );
}
