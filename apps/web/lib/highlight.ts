"use client";

import { useEffect, useState } from "react";
import type { HighlighterCore, ThemedToken } from "shiki/core";

/** Syntax highlighting with shiki, loaded on first use. Tokens carry both theme colours
 *  (--shiki-light / --shiki-dark), so switching the app theme needs no re-highlighting. */

const LIGHT = "github-light-default";
const DARK = "github-dark-default";
const MAX_LINES = 5000; // bigger files show as plain text rather than stall the drawer

const BY_EXT: Record<string, string> = {
  ts: "typescript", mts: "typescript", cts: "typescript", tsx: "tsx", js: "javascript", mjs: "javascript",
  cjs: "javascript", jsx: "jsx", py: "python", pyi: "python", java: "java", kt: "kotlin", kts: "kotlin",
  go: "go", rs: "rust", rb: "ruby", php: "php", cs: "csharp", c: "c", h: "c", cpp: "cpp", cc: "cpp",
  cxx: "cpp", hpp: "cpp", m: "objective-c", swift: "swift", scala: "scala", dart: "dart", lua: "lua",
  r: "r", sh: "bash", bash: "bash", zsh: "bash", ps1: "powershell", sql: "sql", json: "json",
  jsonc: "jsonc", yml: "yaml", yaml: "yaml", toml: "toml", ini: "ini", md: "markdown", mdx: "mdx",
  html: "html", htm: "html", css: "css", scss: "scss", less: "less", vue: "vue", svelte: "svelte",
  xml: "xml", gradle: "groovy", groovy: "groovy", tf: "hcl", hcl: "hcl", proto: "proto",
  graphql: "graphql", gql: "graphql", prisma: "prisma", ex: "elixir", exs: "elixir", erl: "erlang",
  hs: "haskell", clj: "clojure", zig: "zig", nix: "nix", sol: "solidity",
};
const BY_NAME: Record<string, string> = {
  dockerfile: "docker", makefile: "make", "cmakelists.txt": "cmake", gemfile: "ruby", rakefile: "ruby",
  ".env.example": "dotenv", ".gitignore": "gitignore",
};

/** Shiki language id for a path, or null for plain text. */
export function langFor(path: string): string | null {
  const name = path.split("/").pop()?.toLowerCase() || "";
  if (BY_NAME[name]) return BY_NAME[name];
  if (name.startsWith("dockerfile")) return "docker";
  const ext = name.includes(".") ? name.split(".").pop()! : "";
  return BY_EXT[ext] ?? null;
}

/** Shiki language id for a fence tag (```py, ```ts, ```shell…), or null. */
export function fenceLang(tag: string | null): string | null {
  if (!tag) return null;
  const alias: Record<string, string> = { shell: "bash", console: "bash", text: "", plaintext: "", txt: "" };
  if (tag in alias) return alias[tag] || null;
  return BY_EXT[tag] ?? tag; // full names (python, typescript…) pass through; unknown ones fall back to plain text
}

/** Human label for the drawer header ("TypeScript", "Python"…). */
export function langLabel(lang: string | null): string {
  if (!lang) return "Plain text";
  const special: Record<string, string> = {
    typescript: "TypeScript", tsx: "TSX", javascript: "JavaScript", jsx: "JSX", csharp: "C#", cpp: "C++",
    "objective-c": "Objective-C", php: "PHP", sql: "SQL", json: "JSON", jsonc: "JSON", yaml: "YAML",
    toml: "TOML", html: "HTML", css: "CSS", scss: "SCSS", graphql: "GraphQL", hcl: "HCL", mdx: "MDX",
  };
  return special[lang] ?? lang.charAt(0).toUpperCase() + lang.slice(1);
}

let core: Promise<HighlighterCore> | null = null;

function highlighter(): Promise<HighlighterCore> {
  core ??= (async () => {
    const [{ createHighlighterCore }, { createJavaScriptRegexEngine }, { bundledThemes }] = await Promise.all([
      import("shiki/core"),
      import("shiki/engine/javascript"),
      import("shiki/themes"),
    ]);
    return createHighlighterCore({
      themes: [bundledThemes[LIGHT], bundledThemes[DARK]],
      langs: [],
      engine: createJavaScriptRegexEngine({ forgiving: true }),
    });
  })();
  core.catch(() => (core = null));
  return core;
}

async function tokenize(code: string, lang: string): Promise<ThemedToken[][] | null> {
  const h = await highlighter();
  if (!h.getLoadedLanguages().includes(lang)) {
    const { bundledLanguages } = await import("shiki/langs");
    const load = bundledLanguages[lang as keyof typeof bundledLanguages];
    if (!load) return null;
    await h.loadLanguage(load);
  }
  return h.codeToTokens(code, { lang, themes: { light: LIGHT, dark: DARK }, defaultColor: false }).tokens;
}

/** Highlighted lines for `code`, or null until ready (or when the language is unknown):
 *  callers render plain text meanwhile, so nothing waits on the highlighter. */
export function useTokens(code: string | null, lang: string | null): ThemedToken[][] | null {
  const [tokens, setTokens] = useState<ThemedToken[][] | null>(null);
  useEffect(() => {
    setTokens(null);
    if (code == null || !lang || code.split("\n").length > MAX_LINES) return;
    let live = true;
    tokenize(code, lang)
      .then((t) => live && setTokens(t))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [code, lang]);
  return tokens;
}
