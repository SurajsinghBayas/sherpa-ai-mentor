"use client";

import { useEffect, useState } from "react";
import { Command } from "cmdk";
import { Dialog } from "@base-ui/react/dialog";
import { Search } from "lucide-react";
import { cn } from "../lib/utils";
import { Kbd } from "./ui/primitives";

export type PaletteItem = {
  id: string;
  group: string;
  label: string;
  hint?: string;
  icon?: React.ReactNode;
  keywords?: string[];
  run: () => void;
};

/** ⌘K / Ctrl+K: jump between panels and repositories, or start an action. No open/close animation:
 *  it is a keyboard tool used many times a day, so it should feel instant. */
export function CommandPalette({
  open,
  onOpenChange,
  items,
  onAsk,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  items: PaletteItem[];
  /** free text that matches nothing becomes a question for Sherpa */
  onAsk?: (q: string) => void;
}) {
  const [search, setSearch] = useState("");
  useEffect(() => {
    if (open) setSearch("");
  }, [open]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        onOpenChange(!open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  const groups = [...new Set(items.map((i) => i.group))];

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-modal bg-navy-deep/30" />
        <Dialog.Popup className="fixed left-1/2 top-[14dvh] z-modal w-[min(36rem,calc(100vw-2rem))] -translate-x-1/2 overflow-hidden rounded-xl border border-border bg-popover text-popover-foreground shadow-pop outline-none">
          <Dialog.Title className="sr-only">Command menu</Dialog.Title>
          <Command loop className="flex max-h-[min(28rem,70dvh)] flex-col">
                  <div className="flex items-center gap-2 border-b border-border px-3">
                    <Search className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                    <Command.Input
                      autoFocus
                      placeholder="Search panels, repositories, actions…"
                      value={search}
                      onValueChange={setSearch}
                      onKeyDown={(e) => {
                        // Enter with no match asks Sherpa
                        if (e.key === "Enter" && onAsk && search.trim() && !document.querySelector("[cmdk-item][data-selected=true]")) {
                          onAsk(search.trim());
                          onOpenChange(false);
                        }
                      }}
                      className="h-12 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted-foreground"
                    />
                    <Kbd>esc</Kbd>
                  </div>
                  <Command.List className="scroll-thin overflow-y-auto p-1.5">
                    <Command.Empty className="px-3 py-6 text-center text-sm text-muted-foreground">
                      {onAsk ? "Press Enter to ask Sherpa this question." : "Nothing matches."}
                    </Command.Empty>
                    {groups.map((g) => (
                      <Command.Group
                        key={g}
                        heading={g}
                        className="[&_[cmdk-group-heading]]:eyebrow [&_[cmdk-group-heading]]:px-2.5 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:pt-2.5"
                      >
                        {items
                          .filter((i) => i.group === g)
                          .map((i) => (
                            <Command.Item
                              key={i.id}
                              value={`${i.group} ${i.label} ${i.id}`}
                              keywords={i.keywords}
                              onSelect={() => {
                                onOpenChange(false);
                                i.run();
                              }}
                              className={cn(
                                "flex cursor-default select-none items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm",
                                "data-[selected=true]:bg-secondary [&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:text-muted-foreground"
                              )}
                            >
                              {i.icon}
                              <span className="min-w-0 flex-1 truncate">{i.label}</span>
                              {i.hint && <span className="shrink-0 text-xs text-muted-foreground">{i.hint}</span>}
                            </Command.Item>
                          ))}
                      </Command.Group>
                    ))}
                  </Command.List>
          </Command>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
