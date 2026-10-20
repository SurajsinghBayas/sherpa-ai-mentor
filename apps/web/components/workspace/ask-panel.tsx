"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { ArrowUp, ChevronDown } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, type AskResponse } from "../../lib/api";
import { CitationChip } from "../code-viewer";
import { Markdown } from "../markdown";
import { SherpaAvatar, TypingIndicator } from "../sherpa-orb";
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
          className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
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

function Bubble({ msg, isLast }: { msg: ChatMessage; isLast: boolean }) {
  const user = msg.role === "user";
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease }}
      className={cn("flex gap-3", user ? "justify-end" : "justify-start")}
    >
      {!user && <SherpaAvatar state={isLast ? "responding" : "idle"} className="mt-1 shrink-0" />}
      <div className={cn("min-w-0", user ? "max-w-[80%]" : "max-w-[min(100%,46rem)] flex-1")}>
        <div
          className={cn(
            "rounded-2xl px-4 py-3 text-sm",
            user
              ? "rounded-tr-sm bg-primary text-primary-foreground"
              : "rounded-tl-sm border border-border bg-card"
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
        { id: uid(), role: "sherpa", text: "Sorry — I couldn't answer that. The error was shown above; please try again." },
      ]);
    } finally {
      setThinking(false);
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div className="custom-scroll flex-1 space-y-5 overflow-y-auto p-4 sm:p-6">
        {messages.length === 0 && (
          <div className="mx-auto max-w-2xl py-8 text-center">
            <SherpaAvatar state="idle" className="mx-auto" />
            <h3 className="mt-4 font-semibold">
              {repoId ? `Ask anything about ${repoName}` : "Index a repository to start"}
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Every answer cites the exact files and lines it's based on — click a citation to check it.
            </p>
            {repoId && (
              <div className="mt-6 grid gap-2 sm:grid-cols-2">
                {STARTERS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="rounded-xl border border-border bg-card px-4 py-3 text-left text-sm text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        {messages.map((m, i) => (
          <Bubble key={m.id} msg={m} isLast={i === messages.length - 1 && !thinking} />
        ))}
        {thinking && (
          <div className="flex items-start gap-3">
            <SherpaAvatar state="thinking" className="mt-1 shrink-0" />
            <TypingIndicator />
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-border bg-card/60 p-3 sm:p-4">
        <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-xl border border-border bg-background px-3 py-2 transition-shadow focus-within:ring-2 focus-within:ring-ring">
          <Textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={repoId ? "Ask how or why something works…" : "Index a repo to start asking questions"}
            rows={1}
            className="max-h-[140px] min-h-[20px] flex-1 resize-none border-0 bg-transparent p-0 text-sm shadow-none focus-visible:ring-0"
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
        <p className="mt-1.5 text-center text-[10px] text-muted-foreground">
          Enter to send · Shift+Enter for a new line · follow-ups keep context
        </p>
      </div>
    </div>
  );
}
