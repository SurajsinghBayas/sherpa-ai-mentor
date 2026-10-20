"use client";

import { useEffect, useId, useState } from "react";

/** Renders a Mermaid diagram client-side; falls back to the source text if it can't. */
export function MermaidDiagram({ code }: { code: string }) {
  const id = "m" + useId().replace(/[^a-zA-Z0-9]/g, "");
  const [svg, setSvg] = useState("");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        const dark = document.documentElement.classList.contains("dark");
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: "base",
          themeVariables: dark
            ? {
                darkMode: true, background: "transparent", fontSize: "13px",
                primaryColor: "#18181b", primaryTextColor: "#e4e4e7", primaryBorderColor: "#3f3f46",
                lineColor: "#52525b", clusterBkg: "#0f0f11", clusterBorder: "#27272a",
                titleColor: "#a1a1aa", edgeLabelBackground: "#18181b", tertiaryTextColor: "#a1a1aa",
              }
            : {
                background: "transparent", fontSize: "13px", primaryColor: "#ffffff",
                primaryTextColor: "#18181b", primaryBorderColor: "#d4d4d8", lineColor: "#a1a1aa",
                clusterBkg: "#fafafa", clusterBorder: "#e4e4e7", titleColor: "#52525b",
                edgeLabelBackground: "#ffffff",
              },
          fontFamily: "Geist, system-ui, sans-serif",
          flowchart: { curve: "basis", htmlLabels: true, padding: 12 },
        });
        const { svg } = await mermaid.render(id, code);
        if (!cancelled) setSvg(svg);
      } catch (e) {
        console.warn("mermaid render failed", e);
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code, id]);

  if (failed) {
    return (
      <pre className="code-scroll overflow-x-auto rounded-xl bg-black/60 p-4 font-mono text-xs text-zinc-300">{code}</pre>
    );
  }
  if (!svg) return <div className="h-64 animate-pulse rounded-xl bg-secondary/50" />;
  return (
    <div
      className="code-scroll overflow-x-auto rounded-xl border border-border bg-card p-4 [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-none"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
