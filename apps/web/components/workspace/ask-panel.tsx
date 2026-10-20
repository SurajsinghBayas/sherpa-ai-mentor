"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { ArrowUp, ChevronDown } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, type AskResponse } from "../../lib/api";
import { CitationChip } from "../code-viewer";
import { Markdown } from "../markdown";
import { Sherpa, SherpaAvatar, SherpaSays } from "../sherpa";
import { Button, Textarea } from "../ui/primitives";
import { cn } from "../../lib/utils";
import { ease, ModeBadge, VerifiedBadge } from "./shared";

interface ChatMessage {
  id: string;
  role: "user" | "sherpa";
  text: string;
  meta?: AskResponse;
}

const STARTERS = [
  "What happens when a user signs up?",
  "Where is authentication handled?",
  "What is the entrypoint of the app and how does a request flow?",
  "How is data stored and validated?",
];

const uid = () => Math.random().toString(36).slice(2);

function Sources({ meta }: { meta: AskResponse }) {
  const [open, setOpen] = useState(false);
  if (!meta.citations.length) return null;
  return (
    <div className="mt-2 space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <VerifiedBadge n={meta.verify.verified} dropped={meta.verify.unchecked_claims.length} />
        <ModeBadge mode={meta.mode} model={meta.model} />
        <button
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="inline-flex items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
        >
          {open ? "Hide" : "Show"} sources
          <ChevronDown className={cn("size-3 transition-transform", open && "rotate-180")} />
        </button>
      </div>
      {open && (
        <div className="flex flex-wrap gap-1">
          {meta.citations.map((c, i) => (
            <CitationChip key={i} file={c.file} start={c.start_line} end={c.end_line} />
          ))}
        </div>
      )}
    </div>
  );
}

function Bubble({ msg }: { msg: ChatMessage }) {
  const user = msg.role === "user";
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease }}
      className={cn("flex gap-3", user ? "justify-end" : "justify-start")}
    >
      {!user && <SherpaAvatar className="mt-0.5" />}
      <div className={cn("min-w-0", user ? "max-w-[80%]" : "max-w-[min(100%,46rem)] flex-1")}>
        <div
          className={cn(
            "text-sm",
            user ? "rounded-lg bg-foreground px-3.5 py-2.5 text-background" : "pt-1 leading-relaxed"
          )}
        >
          {user ? <p className="whitespace-pre-wrap">{msg.text}</p> : <Markdown text={msg.text} />}
        </div>
        {msg.meta && <Sources meta={msg.meta} />}
      </div>
    </motion.div>
  );
}

export function AskPanel({
  repoId,
  repoName,
  seed,
  onSeedUsed,
}: {
  repoId: string;
  repoName: string;
  seed: string;
  onSeedUsed: () => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, thinking]);

  useEffect(() => {
    if (seed) {
      setInput(seed);
      onSeedUsed();
      inputRef.current?.focus();
    }
  }, [seed, onSeedUsed]);

  async function send(text?: string) {
    const q = (text ?? input).trim();
    if (!q || thinking || !repoId) return;
    setInput("");
    const history = messages.slice(-6).map((m) => ({ role: m.role, text: m.text.slice(0, 600) }));
    setMessages((prev) => [...prev, { id: uid(), role: "user", text: q }]);
    setThinking(true);
    try {
      const r = await api.ask(repoId, q, history);
      setMessages((prev) => [...prev, { id: uid(), role: "sherpa", text: r.answer_markdown, meta: r }]);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Request failed");
      setMessages((prev) => [
        ...prev,
        { id: uid(), role: "sherpa", text: "Sorry, I couldn't answer that. The error is shown in the corner; please try again." },
      ]);
    } finally {
      setThinking(false);
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="scroll-thin flex-1 space-y-5 overflow-y-auto p-4 sm:p-6">
        {messages.length === 0 && (
          <div className="mx-auto max-w-2xl py-6">
            <SherpaSays pose="explaining" size={80} className="max-w-lg">
              {repoId ? (
                <>
                  Ask me anything about <span className="font-semibold">{repoName}</span>. I&apos;ll answer from the code and
                  show the exact files and lines, so you can check me.
                </>
              ) : (
                "Add a repository first, then ask me how anything in it works."
              )}
            </SherpaSays>
            {repoId && (
              <>
                <p className="eyebrow mb-2 mt-8">Try asking</p>
                <div className="grid gap-2 sm:grid-cols-2">
                  {STARTERS.map((s) => (
                    <button
                      key={s}
                      onClick={() => send(s)}
                      className="rounded-lg border border-border bg-card px-3.5 py-3 text-left text-sm text-muted-foreground shadow-card transition-[color,border-color,transform] duration-150 hover:border-input hover:text-foreground active:scale-[0.99]"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
        {messages.map((m) => (
          <Bubble key={m.id} msg={m} />
        ))}
        {thinking && (
          <div className="flex items-center gap-3" role="status">
            <Sherpa pose="thinking" size={48} decorative className="-my-2 -ml-2" />
            <span className="text-sm text-muted-foreground">Reading the code…</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="pb-safe border-t border-border bg-background p-3 sm:p-4">
        <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-xl border border-input bg-card px-3 py-2 shadow-card transition-[border-color,box-shadow] duration-150 focus-within:border-ring focus-within:ring-[3px] focus-within:ring-ring/20">
          <Textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={repoId ? "Ask how or why something works…" : "Index a repo to start asking questions"}
            rows={1}
            aria-label="Your question"
            className="max-h-[140px] min-h-[20px] flex-1 resize-none border-0 bg-transparent p-0 py-1 text-sm shadow-none focus-visible:ring-0"
            disabled={!repoId || thinking}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
          <Button
            size="icon-sm"
            onClick={() => send()}
            disabled={!repoId || !input.trim() || thinking}
            className="shrink-0 rounded-lg"
            aria-label="Send"
          >
            <ArrowUp className="size-4" />
          </Button>
        </div>
        <p className="mt-1.5 hidden text-center text-[11px] text-muted-foreground sm:block">
          Enter to send · Shift+Enter for a new line · follow-ups keep context
        </p>
      </div>
    </div>
  );
}
