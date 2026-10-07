# Sherpa UI/UX system

Distilled from [ibelick/ui-skills](https://github.com/ibelick/ui-skills) (baseline-ui, motion)
and [emilkowalski/skills](https://github.com/emilkowalski/skills) (agents-with-taste, animation rules).
Single source of truth for every screen in `apps/web`.

## Stack

- **Shadcn-style primitives** (`components/ui/primitives.tsx`): Button, Card, Input, Textarea, Label, Badge, Tabs, Separator, Skeleton — cva variants, `cn()` merging.
- **Fonts:** [Geist](https://fonts.google.com/specimen/Geist) for UI, [Geist Mono](https://fonts.google.com/specimen/Geist+Mono) for code/ids (`font-mono`).
- **Icons:** [lucide-react](https://lucide.dev) — 1.5px-stroke outline style, same language as Hugeicons/Keyline/Morphicons sets. Rule: one icon per action, `size-4` in buttons, never emoji as icon.
- **Toasts:** [Sonner](https://sonner.emilkowal.ski) (`richColors`, bottom-right) — success/error only, no toasts for loading (use inline spinners).
- **Motion:** CSS keyframes + framer-motion for tab transitions and scroll reveals.

## Motion rules (non-negotiable)

1. **Enters use ease-out** (`cubic-bezier(0.22, 1, 0.36, 1)`), never ease-in — objects arrive fast and settle soft.
2. **Durations:** micro (hover/active) 150–200ms · reveals 400–550ms · stagger 60ms steps.
3. **Active press:** `active:scale-[0.98]` on every button.
4. **Depth via soft shadow**, not solid borders: `shadow-[0_1px_2px_rgba(0,0,0,0.04)]` on cards, lifted `-translate-y-1` on hover.
5. **Tab switches:** fade + 10px rise, 250ms, `AnimatePresence mode="wait"`.
6. **Reduced motion** respected globally in `globals.css`.
7. **Skeletons** for auth-gated loading, never blank screens or layout shift.

## Robustness (break-ui checklist)

- Long repo URLs / emails: truncate with `truncate`, full value in `title`.
- Empty states everywhere: no repo → hint card; no keys → inline “add one” CTA; no citations → confidence badge explains why.
- Worst-case content: 500-line answers scroll inside cards (`whitespace-pre-wrap`), code blocks scroll horizontally (`code-scroll`).
- Forms: inline `required` + server `detail` surfaced via toast, fields keep their values.

## Dark mode

Token-based (`.dark` on `<html>`), all color through CSS vars. Toggle hook point: `document.documentElement.classList`.
