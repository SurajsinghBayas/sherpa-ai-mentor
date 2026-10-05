import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    container: { center: true, padding: "1.5rem", screens: { "2xl": "1280px" } },
    extend: {
      fontFamily: {
        sans: ["Geist", "system-ui", "-apple-system", "sans-serif"],
        mono: ["Geist Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        sherpa: {
          glow: "hsl(var(--sherpa-glow))",
          dot: "hsl(var(--sherpa-dot))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        xl: "calc(var(--radius) + 4px)",
        "2xl": "calc(var(--radius) + 8px)",
      },
      spacing: {
        "18": "4.5rem",
        "22": "5.5rem",
      },
      keyframes: {
        /* page transitions */
        enter: {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "enter-up": {
          from: { opacity: "0", transform: "translateY(14px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.96)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        /* Sherpa orb */
        "orb-breathe": {
          "0%, 100%": { transform: "scale(1)" },
          "50%": { transform: "scale(1.06)" },
        },
        "orb-spin": {
          from: { transform: "rotate(0deg)" },
          to: { transform: "rotate(360deg)" },
        },
        "dot-float-1": {
          "0%, 100%": { transform: "translate(0, 0)" },
          "33%": { transform: "translate(2px, -3px)" },
          "66%": { transform: "translate(-2px, 1px)" },
        },
        "dot-float-2": {
          "0%, 100%": { transform: "translate(0, 0)" },
          "33%": { transform: "translate(-2px, 2px)" },
          "66%": { transform: "translate(3px, -2px)" },
        },
        "dot-float-3": {
          "0%, 100%": { transform: "translate(0, 0)" },
          "33%": { transform: "translate(3px, 1px)" },
          "66%": { transform: "translate(-1px, -3px)" },
        },
        /* shimmer loading */
        shimmer: {
          from: { backgroundPosition: "200% center" },
          to: { backgroundPosition: "-200% center" },
        },
        /* chat message appear */
        "message-in": {
          from: { opacity: "0", transform: "translateY(6px) scale(0.98)" },
          to: { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        /* typing indicator dots */
        "typing-dot": {
          "0%, 60%, 100%": { transform: "translateY(0)" },
          "30%": { transform: "translateY(-4px)" },
        },
        /* floating for hero elements */
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%": { transform: "translateY(-8px)" },
        },
      },
      animation: {
        enter: "enter 0.6s cubic-bezier(0.22,1,0.36,1) both",
        "enter-up": "enter-up 0.55s cubic-bezier(0.22,1,0.36,1) both",
        "fade-in": "fade-in 0.4s ease-out both",
        "scale-in": "scale-in 0.3s cubic-bezier(0.22,1,0.36,1) both",
        "slide-up": "slide-up 0.4s cubic-bezier(0.22,1,0.36,1) both",
        "orb-breathe": "orb-breathe 4s ease-in-out infinite",
        "orb-spin": "orb-spin 2s linear infinite",
        "dot-float-1": "dot-float-1 3.5s ease-in-out infinite",
        "dot-float-2": "dot-float-2 4s ease-in-out infinite 0.5s",
        "dot-float-3": "dot-float-3 3.8s ease-in-out infinite 1s",
        shimmer: "shimmer 2.5s linear infinite",
        "message-in": "message-in 0.3s cubic-bezier(0.22,1,0.36,1) both",
        "typing-dot": "typing-dot 1.2s ease-in-out infinite",
        float: "float 6s ease-in-out infinite",
      },
      backgroundImage: {
        "hero-grid":
          "linear-gradient(hsl(var(--border)) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--border)) 1px, transparent 1px)",
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        shimmer:
          "linear-gradient(90deg, transparent 0%, hsl(var(--muted-foreground)/0.08) 50%, transparent 100%)",
      },
      backgroundSize: {
        "hero-grid": "48px 48px",
      },
      boxShadow: {
        card: "0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)",
        "card-hover": "0 4px 12px rgba(0,0,0,0.08), 0 2px 4px rgba(0,0,0,0.06)",
        orb: "0 0 30px hsl(var(--sherpa-glow)/0.35), 0 0 60px hsl(var(--sherpa-glow)/0.15)",
        "orb-sm": "0 0 16px hsl(var(--sherpa-glow)/0.3)",
        "inner-sm": "inset 0 1px 0 rgba(255,255,255,0.06)",
      },
    },
  },
  plugins: [],
};

export default config;
