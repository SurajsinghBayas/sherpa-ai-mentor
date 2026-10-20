import type { Config } from "tailwindcss";

const token = (name: string) => `hsl(var(--${name}) / <alpha-value>)`;

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    container: { center: true, padding: "1rem", screens: { sm: "640px", md: "768px", lg: "1024px", xl: "1200px" } },
    extend: {
      fontFamily: {
        sans: ["Geist", "system-ui", "-apple-system", "sans-serif"],
        mono: ["Geist Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        border: token("border"),
        input: token("input"),
        ring: token("ring"),
        background: token("background"),
        foreground: token("foreground"),
        primary: { DEFAULT: token("primary"), foreground: token("primary-foreground") },
        secondary: { DEFAULT: token("secondary"), foreground: token("secondary-foreground") },
        destructive: { DEFAULT: token("destructive"), foreground: token("destructive-foreground") },
        muted: { DEFAULT: token("muted"), foreground: token("muted-foreground") },
        accent: { DEFAULT: token("accent"), foreground: token("accent-foreground") },
        card: { DEFAULT: token("card"), foreground: token("card-foreground") },
        popover: { DEFAULT: token("popover"), foreground: token("popover-foreground") },
        success: token("success"),
        warning: token("warning"),
        /* code surfaces stay navy in both themes, like the brand's dark card */
        code: { DEFAULT: token("code"), foreground: token("code-foreground"), muted: token("code-muted"), line: token("code-line") },
        /* brand palette (style guide) */
        navy: { DEFAULT: "#17223D", deep: "#101827" },
        sky: { brand: "#A9D5FF" },
        cream: "#FFF5E7",
        tan: "#F2A65A",
        bark: { DEFAULT: "#8B572A", dark: "#54351F" },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        xl: "calc(var(--radius) + 4px)",
        "2xl": "calc(var(--radius) + 8px)",
      },
      zIndex: { header: "40", popover: "50", overlay: "60", modal: "70", toast: "80" },
      transitionTimingFunction: {
        out: "cubic-bezier(0.23, 1, 0.32, 1)",
        "in-out": "cubic-bezier(0.77, 0, 0.175, 1)",
      },
      keyframes: {
        "enter-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        pulse: { "0%, 100%": { opacity: "1" }, "50%": { opacity: "0.45" } },
      },
      animation: {
        "enter-up": "enter-up 0.24s cubic-bezier(0.23,1,0.32,1) both",
        "fade-in": "fade-in 0.2s ease-out both",
        pulse: "pulse 1.6s ease-in-out infinite",
      },
      boxShadow: {
        card: "0 1px 2px rgb(23 34 61 / 0.05)",
        pop: "0 8px 24px -6px rgb(23 34 61 / 0.18), 0 2px 6px rgb(23 34 61 / 0.06)",
        /* hard offset shadow: echoes the pixel art without a glow */
        pixel: "3px 3px 0 0 rgb(23 34 61)",
        "pixel-sm": "2px 2px 0 0 rgb(23 34 61)",
      },
    },
  },
  plugins: [],
};

export default config;
