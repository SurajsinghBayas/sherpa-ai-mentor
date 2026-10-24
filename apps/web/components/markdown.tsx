"use client";

import ReactMarkdown, { defaultUrlTransform, type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { createContext, isValidElement, useContext } from "react";
import { GitCommitHorizontal } from "lucide-react";
import { CitationChip } from "./code-viewer";
import { CodeSnippet } from "./source-code";
import { fenceLang } from "../lib/highlight";
import { cn } from "../lib/utils";
import type { CommitRef } from "../lib/api";

// [path/to/file.py:12-30] → a markdown link with a cite: href, rendered as a chip.
const CITE = /\[([^\[\]\s:]+?):L?(\d+)(?:\s*[-–]\s*L?(\d+))?\](?!\()/g;

// [path:12-30](anything) → [path:12-30]: models sometimes give a citation a link target (even file:///…)
const CITE_LINK = /(\[[^\[\]\s:]+?:L?\d+(?:\s*[-–]\s*L?\d+)?\])\((?:[^()\n]|\([^()\n]*\))*\)/g;

// [commit 1a2b3c4] → a commit: link, rendered as a chip that opens the commit on its host.
const COMMIT = /\[commit ([0-9a-f]{6,40})\](?!\()/gi;
const Commits = createContext<CommitRef[]>([]);

export function CommitChip({ sha, commit }: { sha: string; commit?: CommitRef }) {
  const known = useContext(Commits);
  const c = commit ?? known.find((x) => x.sha.startsWith(sha) || sha.startsWith(x.short));
  const when = c ? new Date(c.t * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "";
  const title = c ? `${c.subject}${c.author ? ` · ${c.author}` : ""} · ${when}` : `commit ${sha}`;
  const body = (
    <>
      <GitCommitHorizontal className="size-3" />
      {sha.slice(0, 7)}
    </>
  );
  const cls = "mx-0.5 inline-flex items-center gap-1 rounded border border-border bg-secondary px-1.5 py-px align-baseline font-mono text-[11px] text-foreground no-underline transition-colors hover:border-primary/40 hover:text-primary";
  return c?.url ? (
    <a href={c.url} target="_blank" rel="noreferrer" title={title} className={cls}>{body}</a>
  ) : (
    <span title={title} className={cls}>{body}</span>
  );
}

function linkCitations(md: string): string {
  // leave fenced code blocks untouched
  return md
    .split(/(```[\s\S]*?```)/g)
    .map((part, i) =>
      i % 2 === 1
        ? part
        : part
            .replace(CITE_LINK, "$1")
            .replace(CITE, (_m, file: string, a: string, b?: string) => {
              const end = b ?? a;
              return `[${file}:${a}-${end}](cite:${encodeURIComponent(file)}:${a}:${end})`;
            })
            .replace(COMMIT, (_m, sha: string) => `[${sha.toLowerCase()}](commit:${sha.toLowerCase()})`)
    )
    .join("");
}

const components: Components = {
  a({ href, children }) {
    if (href?.startsWith("cite:")) {
      const [, file, a, b] = href.match(/^cite:(.+):(\d+):(\d+)$/) || [];
      if (file) return <CitationChip file={decodeURIComponent(file)} start={+a} end={+b} variant="inline" />;
    }
    if (href?.startsWith("commit:")) return <CommitChip sha={href.slice(7)} />;
    if (!href || !/^(https?:|mailto:)/i.test(href)) {
      // not a web link: a model-made repo reference ([a.py:3-9](…), [main.py](main.py), [x](src/x.py#L4-L9)).
      // Opening it would load this app's own page in a new tab, so open the code viewer instead.
      const label = typeof children === "string" ? children : Array.isArray(children) && children.length === 1 && typeof children[0] === "string" ? children[0] : "";
      const lc = /^`?([^\s:`]+):L?(\d+)(?:\s*[-–]\s*L?(\d+))?`?$/.exec(label.trim());
      if (lc) return <CitationChip file={lc[1]} start={+lc[2]} end={+(lc[3] ?? lc[2])} variant="inline" />;
      const path = (href ?? "").replace(/^\.?\//, "");
      const anchor = /#L(\d+)(?:-L?(\d+))?$/.exec(path);
      if (path && /^[\w@./-]+\.[\w]+(#L\d+(-L?\d+)?)?$/.test(path)) {
        const file = path.replace(/#.*$/, "");
        const a = anchor ? +anchor[1] : 1;
        return <CitationChip file={file} start={a} end={anchor?.[2] ? +anchor[2] : a} variant="inline" />;
      }
      return <span className="font-medium">{children}</span>;
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
  pre: ({ children }) => {
    // react-markdown hands us <pre><code class="language-x">…</code></pre>
    const child = isValidElement<{ className?: string; children?: React.ReactNode }>(children) ? children : null;
    const lang = /language-([\w+#-]+)/.exec(child?.props.className || "")?.[1]?.toLowerCase() ?? null;
    return <CodeSnippet code={String(child?.props.children ?? "")} lang={fenceLang(lang)} className="my-3" />;
  },
  code({ className, children }) {
    const block = /language-/.test(className || "") || String(children).includes("\n");
    if (block) return <code className={className}>{children}</code>;
    return (
      <code className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[0.85em] text-foreground">{children}</code>
    );
  },
};

export function Markdown({ text, className, commits = [] }: { text: string; className?: string; commits?: CommitRef[] }) {
  return (
    <Commits.Provider value={commits}>
    <div className={cn("text-sm text-card-foreground [overflow-wrap:anywhere]", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={components}
        // keep our cite: links; everything else goes through the safe default (no javascript: etc.)
        urlTransform={(url) => (url.startsWith("cite:") || url.startsWith("commit:") ? url : defaultUrlTransform(url))}
      >
        {linkCitations(text)}
      </ReactMarkdown>
    </div>
    </Commits.Provider>
  );
}
