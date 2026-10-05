"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

/* ---------- Button ---------- */
const buttonVariants = cva(
  [
    "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium",
    "transition-all duration-200 ease-out",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1",
    "disabled:pointer-events-none disabled:opacity-40",
    "active:scale-[0.97]",
    "[&_svg]:size-4 [&_svg]:shrink-0",
  ].join(" "),
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground shadow-sm hover:opacity-88",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/70",
        outline:
          "border border-border bg-transparent hover:bg-accent hover:text-accent-foreground",
        ghost:
          "hover:bg-accent hover:text-accent-foreground",
        destructive:
          "bg-destructive text-destructive-foreground shadow-sm hover:opacity-88",
        link:
          "text-primary underline-offset-4 hover:underline p-0 h-auto",
        glow:
          "bg-primary text-primary-foreground shadow-orb hover:opacity-88",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-10 rounded-lg px-6",
        xl: "h-12 rounded-xl px-8 text-base",
        icon: "h-9 w-9 rounded-lg",
        "icon-sm": "h-7 w-7 rounded-md",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

export function Button({
  className,
  variant,
  size,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants>) {
  return (
    <button
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}

/* ---------- Card ---------- */
export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-card text-card-foreground shadow-card",
        className
      )}
      {...props}
    />
  );
}
export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col space-y-1.5 p-6", className)} {...props} />;
}
export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3 className={cn("text-base font-semibold leading-none tracking-tight", className)} {...props} />
  );
}
export function CardDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-sm text-muted-foreground leading-relaxed", className)} {...props} />;
}
export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-6 pt-0", className)} {...props} />;
}
export function CardFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex items-center p-6 pt-0", className)} {...props} />;
}

/* ---------- Input / Textarea / Label ---------- */
export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "flex h-9 w-full rounded-lg border border-input bg-transparent px-3 py-1 text-sm",
        "placeholder:text-muted-foreground",
        "transition-colors duration-150",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        "disabled:opacity-50",
        className
      )}
      {...props}
    />
  );
}
export function Textarea({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "flex min-h-[80px] w-full rounded-lg border border-input bg-transparent px-3 py-2 text-sm",
        "placeholder:text-muted-foreground resize-none",
        "transition-colors duration-150",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        "disabled:opacity-50",
        className
      )}
      {...props}
    />
  );
}
export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn("text-sm font-medium leading-none text-foreground/80", className)}
      {...props}
    />
  );
}

/* ---------- Badge ---------- */
const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors [&_svg]:size-3",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground",
        secondary: "bg-secondary text-secondary-foreground border border-border",
        outline: "border border-border text-foreground bg-transparent",
        success:
          "bg-emerald-500/10 text-emerald-600 border border-emerald-500/20 dark:text-emerald-400",
        warning:
          "bg-amber-500/10 text-amber-600 border border-amber-500/20 dark:text-amber-400",
        info: "bg-blue-500/10 text-blue-600 border border-blue-500/20 dark:text-blue-400",
      },
    },
    defaultVariants: { variant: "default" },
  }
);
export function Badge({
  className,
  variant,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

/* ---------- Separator ---------- */
export function Separator({ className, orientation = "horizontal" }: { className?: string; orientation?: "horizontal" | "vertical" }) {
  return (
    <div
      className={cn(
        "shrink-0 bg-border",
        orientation === "horizontal" ? "h-px w-full" : "h-full w-px",
        className
      )}
    />
  );
}

/* ---------- Skeleton ---------- */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "relative overflow-hidden rounded-md bg-muted",
        "before:absolute before:inset-0 before:bg-shimmer before:bg-[length:200%_100%] before:animate-shimmer",
        className
      )}
      {...props}
    />
  );
}

/* ---------- Tabs ---------- */
export function Tabs({
  value,
  onValueChange,
  tabs,
  className,
}: {
  value: string;
  onValueChange: (v: string) => void;
  tabs: { value: string; label: string; icon?: React.ReactNode }[];
  className?: string;
}) {
  return (
    <div
      className={cn(
        "inline-flex h-9 items-center gap-0.5 rounded-lg bg-secondary p-1",
        className
      )}
    >
      {tabs.map((t) => (
        <button
          key={t.value}
          onClick={() => onValueChange(t.value)}
          className={cn(
            "inline-flex items-center gap-1.5 whitespace-nowrap rounded-md px-3 py-1 text-sm font-medium",
            "transition-all duration-200 ease-out",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            value === t.value
              ? "bg-background text-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          {t.icon}
          {t.label}
        </button>
      ))}
    </div>
  );
}

/* ---------- Select ---------- */
export function Select({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "flex h-9 w-full rounded-lg border border-input bg-transparent px-3 text-sm",
        "text-foreground",
        "focus:outline-none focus:ring-2 focus:ring-ring",
        "disabled:opacity-50",
        className
      )}
      {...props}
    />
  );
}

/* ---------- Tooltip (simple CSS) ---------- */
export function Tooltip({ content, children }: { content: string; children: React.ReactNode }) {
  return (
    <div className="group relative inline-flex">
      {children}
      <span
        className={cn(
          "pointer-events-none absolute bottom-full left-1/2 mb-2 -translate-x-1/2",
          "whitespace-nowrap rounded-md bg-foreground px-2 py-1 text-xs text-background",
          "opacity-0 transition-opacity duration-150 group-hover:opacity-100",
          "shadow-md"
        )}
      >
        {content}
      </span>
    </div>
  );
}
