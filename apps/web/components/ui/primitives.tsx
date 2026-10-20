"use client";

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { AlertDialog } from "@base-ui/react/alert-dialog";
import { Menu as BaseMenu } from "@base-ui/react/menu";
import { Tabs as BaseTabs } from "@base-ui/react/tabs";
import { Tooltip as BaseTooltip } from "@base-ui/react/tooltip";
import { cn } from "../../lib/utils";
import { buttonVariants } from "./button-variants";

/* ---------- Button ---------- */
export { buttonVariants };

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants>;

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { className, variant, size, type = "button", ...props },
  ref
) {
  return <button ref={ref} type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />;
});

/* ---------- Card ---------- */
export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-xl border border-border bg-card text-card-foreground shadow-card", className)} {...props} />;
}
export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("flex flex-col gap-1 p-5", className)} {...props} />;
}
export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h3 className={cn("text-[15px] font-semibold leading-tight", className)} {...props} />;
}
export function CardDescription({ className, ...props }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={cn("text-sm leading-relaxed text-muted-foreground", className)} {...props} />;
}
export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-5 pt-0", className)} {...props} />;
}

/* ---------- Input / Textarea / Label / Select ---------- */
const field =
  "w-full rounded-lg border border-input bg-card px-3 text-sm text-foreground placeholder:text-muted-foreground/80 transition-[border-color,box-shadow] duration-150 focus-visible:border-ring focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/20 disabled:opacity-50 aria-[invalid=true]:border-destructive";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(function Input(
  { className, ...props },
  ref
) {
  return <input ref={ref} className={cn(field, "h-9", className)} {...props} />;
});

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...props }, ref) {
    return <textarea ref={ref} className={cn(field, "min-h-[80px] resize-none py-2", className)} {...props} />;
  }
);

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("text-[13px] font-medium leading-none text-foreground", className)} {...props} />;
}

export function Select({ className, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(field, "h-9 pr-8", className)} {...props} />;
}

/* ---------- Badge ---------- */
const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md border px-1.5 py-px text-[11px] font-medium leading-5 [&_svg]:size-3",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-border bg-secondary text-secondary-foreground",
        outline: "border-border text-muted-foreground",
        success: "border-success/25 bg-success/10 text-success",
        warning: "border-warning/30 bg-warning/10 text-warning",
        info: "border-primary/25 bg-primary/10 text-primary",
      },
    },
    defaultVariants: { variant: "secondary" },
  }
);
export function Badge({ className, variant, ...props }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}

/* ---------- Separator / Skeleton / Kbd ---------- */
export function Separator({ className, orientation = "horizontal" }: { className?: string; orientation?: "horizontal" | "vertical" }) {
  return <div role="separator" className={cn("shrink-0 bg-border", orientation === "horizontal" ? "h-px w-full" : "h-full w-px", className)} />;
}

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("animate-pulse rounded-md bg-secondary", className)} {...props} />;
}

export function Kbd({ className, ...props }: React.HTMLAttributes<HTMLElement>) {
  return (
    <kbd
      className={cn("inline-flex h-5 min-w-5 items-center justify-center rounded border border-border bg-card px-1 font-mono text-[10px] text-muted-foreground", className)}
      {...props}
    />
  );
}

/* ---------- Tabs (Base UI) ---------- */
export function Tabs({
  value,
  onValueChange,
  tabs,
  className,
  label,
}: {
  value: string;
  onValueChange: (v: string) => void;
  tabs: { value: string; label: string; icon?: React.ReactNode }[];
  className?: string;
  label?: string;
}) {
  return (
    <BaseTabs.Root value={value} onValueChange={(v) => onValueChange(String(v))}>
      <BaseTabs.List
        aria-label={label}
        className={cn("no-scrollbar relative flex items-center gap-0.5 overflow-x-auto rounded-lg border border-border bg-secondary p-0.5", className)}
      >
        {tabs.map((t) => (
          <BaseTabs.Tab
            key={t.value}
            value={t.value}
            className={cn(
              "relative z-[1] inline-flex h-8 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-md px-3 text-[13px] font-medium text-muted-foreground",
              "transition-colors duration-150 hover:text-foreground data-[active]:text-foreground [&_svg]:size-3.5"
            )}
          >
            {t.icon}
            {t.label}
          </BaseTabs.Tab>
        ))}
        <BaseTabs.Indicator
          className={cn(
            "absolute left-0 top-1/2 z-0 h-8 w-[var(--active-tab-width)] -translate-y-1/2 translate-x-[var(--active-tab-left)]",
            "rounded-md border border-border bg-card shadow-card transition-[transform,width] duration-200 ease-out"
          )}
        />
      </BaseTabs.List>
    </BaseTabs.Root>
  );
}

/* ---------- Tooltip (Base UI) ---------- */
export const TooltipProvider = BaseTooltip.Provider;

export function Tooltip({
  content,
  children,
  side = "top",
}: {
  content: React.ReactNode;
  children: React.ReactElement;
  side?: "top" | "bottom" | "left" | "right";
}) {
  return (
    <BaseTooltip.Root>
      <BaseTooltip.Trigger render={children} />
      <BaseTooltip.Portal>
        <BaseTooltip.Positioner side={side} sideOffset={6} className="z-popover">
          <BaseTooltip.Popup
            className={cn(
              "origin-[var(--transform-origin)] rounded-md bg-foreground px-2 py-1 text-xs text-background shadow-pop",
              "transition-[transform,opacity] duration-150 ease-out data-[ending-style]:scale-[0.97] data-[ending-style]:opacity-0",
              "data-[starting-style]:scale-[0.97] data-[starting-style]:opacity-0 data-[instant]:duration-0"
            )}
          >
            {content}
          </BaseTooltip.Popup>
        </BaseTooltip.Positioner>
      </BaseTooltip.Portal>
    </BaseTooltip.Root>
  );
}

/* ---------- Menu (Base UI) ---------- */
export const Menu = {
  Root: BaseMenu.Root,
  Trigger: BaseMenu.Trigger,
  Popup({ children, className, align = "start", side = "bottom" }: {
    children: React.ReactNode;
    className?: string;
    align?: "start" | "center" | "end";
    side?: "top" | "bottom";
  }) {
    return (
      <BaseMenu.Portal>
        <BaseMenu.Positioner sideOffset={6} align={align} side={side} className="z-popover outline-none">
          <BaseMenu.Popup
            className={cn(
              "origin-[var(--transform-origin)] rounded-xl border border-border bg-popover p-1 text-popover-foreground shadow-pop outline-none",
              "transition-[transform,opacity] duration-150 ease-out data-[ending-style]:scale-[0.97] data-[ending-style]:opacity-0",
              "data-[starting-style]:scale-[0.97] data-[starting-style]:opacity-0",
              className
            )}
          >
            {children}
          </BaseMenu.Popup>
        </BaseMenu.Positioner>
      </BaseMenu.Portal>
    );
  },
  Item({ className, ...props }: React.ComponentProps<typeof BaseMenu.Item>) {
    return (
      <BaseMenu.Item
        className={cn(
          "flex cursor-default select-none items-center gap-2 rounded-lg px-2.5 py-2 text-sm outline-none",
          "data-[highlighted]:bg-secondary data-[disabled]:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-muted-foreground",
          className as string
        )}
        {...props}
      />
    );
  },
  Separator() {
    return <BaseMenu.Separator className="mx-1 my-1 h-px bg-border" />;
  },
  Label({ children }: { children: React.ReactNode }) {
    return <div className="eyebrow px-2.5 pb-1 pt-2">{children}</div>;
  },
};

/* ---------- Confirm dialog (Base UI AlertDialog) for destructive actions ---------- */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Delete",
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: React.ReactNode;
  confirmLabel?: string;
  onConfirm: () => void;
}) {
  return (
    <AlertDialog.Root open={open} onOpenChange={onOpenChange}>
      <AlertDialog.Portal>
        <AlertDialog.Backdrop className="fixed inset-0 z-modal bg-navy-deep/40 transition-opacity duration-200 ease-out data-[ending-style]:opacity-0 data-[starting-style]:opacity-0" />
        <AlertDialog.Popup
          className={cn(
            "fixed left-1/2 top-1/2 z-modal w-[min(26rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-card p-5 shadow-pop",
            "transition-[transform,opacity] duration-200 ease-out data-[ending-style]:scale-[0.97] data-[ending-style]:opacity-0",
            "data-[starting-style]:scale-[0.97] data-[starting-style]:opacity-0"
          )}
        >
          <AlertDialog.Title className="text-base font-semibold">{title}</AlertDialog.Title>
          <AlertDialog.Description className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{description}</AlertDialog.Description>
          <div className="mt-5 flex justify-end gap-2">
            <AlertDialog.Close render={<Button variant="outline" />}>Cancel</AlertDialog.Close>
            <Button
              variant="destructive"
              onClick={() => {
                onConfirm();
                onOpenChange(false);
              }}
            >
              {confirmLabel}
            </Button>
          </div>
        </AlertDialog.Popup>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}
