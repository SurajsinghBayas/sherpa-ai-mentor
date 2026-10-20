"use client";

import { useEffect, useId, useState } from "react";
import { useTheme } from "next-themes";

/** Renders a Mermaid diagram client-side; falls back to the source text if it can't. */
export function MermaidDiagram({ code }: { code: string }) {
  const id = "m" + useId().replace(/[^a-zA-Z0-9]/g, "");
  const [svg, setSvg] = useState("");
  const [failed, setFailed] = useState(false);
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        const dark = resolvedTheme === "dark";
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: "base",
          themeVariables: dark
            ? {
                darkMode: true, background: "transparent", fontSize: "13px",
                primaryColor: "#17223D", primaryTextColor: "#F3EEE6", primaryBorderColor: "#2F4672",
                lineColor: "#5B9DF5", clusterBkg: "#18191D", clusterBorder: "#2A2C32",
                titleColor: "#9A9DA6", edgeLabelBackground: "#18191D", tertiaryTextColor: "#9A9DA6",
              }
            : {
                background: "transparent", fontSize: "13px", primaryColor: "#FFF5E7",
                primaryTextColor: "#17223D", primaryBorderColor: "#17223D", lineColor: "#2F80ED",
                clusterBkg: "#F8F5F0", clusterBorder: "#E3DCD0", titleColor: "#5D667A",
                edgeLabelBackground: "#FFFFFF",
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
  }, [code, id, resolvedTheme]);

  if (failed) {
    return (
      <pre className="scroll-thin-code overflow-x-auto rounded-xl bg-code p-4 font-mono text-xs text-code-foreground">{code}</pre>
    );
  }
  if (!svg) return <div className="h-64 animate-pulse rounded-xl bg-secondary/50" />;
  return (
    <div
      className="scroll-thin-code overflow-x-auto rounded-xl border border-border bg-card p-4 [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-none"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
