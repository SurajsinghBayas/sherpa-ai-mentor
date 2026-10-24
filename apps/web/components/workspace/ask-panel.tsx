"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowUp, AudioLines, ChevronDown, History, Mic, SquarePen, Trash2, Volume2, VolumeX } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, type AskResponse } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { deleteChat, historySupported, listChats, saveChat, type Chat, type StoredMessage } from "../../lib/chat-history";
import { CitationChip } from "../code-viewer";
import { ListenButton } from "../listen-button";
import { listen, recognitionSupported, say, stop } from "../../lib/voice";
import { CommitChip, Markdown } from "../markdown";
import { Sherpa, SherpaAvatar, SherpaSays } from "../sherpa";
import { Button, Menu, Textarea } from "../ui/primitives";
import { cn } from "../../lib/utils";
import { ease, ModeBadge, timeAgo, VerifiedBadge } from "./shared";
import { VoiceMode } from "./voice-mode";

type ChatMessage = StoredMessage;

const STARTERS = [
  "What happens when a user signs up?",
  "Where is authentication handled?",
  "What is the entrypoint of the app and how does a request flow?",
  "How is data stored and validated?",
];

const uid = () => Math.random().toString(36).slice(2);

function Sources({ meta, id, text }: { meta: AskResponse; id: string; text: string }) {
  const [open, setOpen] = useState(false);
  const commits = meta.commits ?? [];
  if (!meta.citations.length && !commits.length) return <ListenButton id={id} text={text} className="mt-2" />;
  return (
    <div className="mt-2 space-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <VerifiedBadge n={meta.verify.verified} dropped={meta.verify.unchecked_claims.length} />
        <ModeBadge mode={meta.mode} model={meta.model} />
        <ListenButton id={id} text={text} className="ml-1" />
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
          {commits.map((c) => (
            <CommitChip key={c.sha} sha={c.short} commit={c} />
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
          {user ? (
            <p className="whitespace-pre-wrap">
              {msg.voice && <Mic className="mr-1.5 inline size-3.5 -translate-y-px opacity-60" aria-label="Asked by voice" />}
              {msg.text}
            </p>
          ) : (
            <Markdown text={msg.text} commits={msg.meta?.commits} />
          )}
        </div>
        {msg.meta && <Sources meta={msg.meta} id={msg.id} text={msg.text} />}
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
  const [canListen, setCanListen] = useState(false); // the browser can turn speech into text (dictation)
  const [canConverse, setCanConverse] = useState(false); // voice mode: the browser or the API can
  const [listening, setListening] = useState(false);
  const recRef = useRef<{ stop: () => void } | null>(null);
  const [voiceMode, setVoiceMode] = useState(false);
  // read every answer aloud, typed questions too (remembered per browser)
  const [speakAnswers, setSpeakAnswers] = useState(false);
  const history = useRef<ChatMessage[]>([]);
  history.current = messages;

  // conversations are kept on this device: see lib/chat-history.ts
  const { user } = useAuth();
  const [chatId, setChatId] = useState(uid);
  const created = useRef(Date.now());
  const [chats, setChats] = useState<Chat[]>([]);
  const refreshChats = () => {
    if (user && repoId && historySupported()) listChats(user.id, repoId).then(setChats).catch(() => {});
  };

  function newChat() {
    stop();
    setMessages([]);
    setChatId(uid());
    created.current = Date.now();
    inputRef.current?.focus();
  }

  function openChat(c: Chat) {
    stop();
    setMessages(c.messages);
    setChatId(c.id);
    created.current = c.createdAt;
  }

  async function removeChat(id: string) {
    await deleteChat(id).catch(() => {});
    if (id === chatId) newChat();
    refreshChats();
  }

  // another repo (or account): start fresh, with that repo's past chats one click away
  useEffect(() => {
    newChat();
    refreshChats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repoId, user?.id]);

  // save after every turn
  useEffect(() => {
    if (!user || !repoId || !messages.length || !historySupported()) return;
    saveChat({ id: chatId, userId: user.id, repoId, createdAt: created.current, messages })
      .then(refreshChats)
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [messages]);

  useEffect(() => {
    setCanListen(recognitionSupported());
    setCanConverse(recognitionSupported());
    // with Amazon Transcribe on the API, voice mode works in any browser that has a mic
    if (!recognitionSupported() && typeof navigator !== "undefined" && navigator.mediaDevices)
      api.voiceConfig().then((c) => c.stt === "transcribe" && setCanConverse(true), () => {});
    try {
      setSpeakAnswers(localStorage.getItem("sherpa.speakAnswers") === "1");
    } catch {}
  }, []);

  function toggleSpeakAnswers() {
    const on = !speakAnswers;
    setSpeakAnswers(on);
    if (!on) stop();
    try {
      localStorage.setItem("sherpa.speakAnswers", on ? "1" : "0");
    } catch {}
  }
  useEffect(() => () => recRef.current?.stop(), []);

  async function talk() {
    if (listening) return recRef.current?.stop();
    setListening(true);
    try {
      const rec = listen(setInput);
      recRef.current = rec;
      const q = (await rec.done).trim();
      if (q) send(q, true); // a spoken question gets a spoken answer
    } catch (e) {
      toast.error(
        e instanceof Error && e.message === "not-allowed"
          ? "Microphone access is blocked. Allow it in your browser's site settings."
          : "Couldn't hear that. Try again, or type your question."
      );
    } finally {
      recRef.current = null;
      setListening(false);
    }
  }

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

  /** Ask in the chat. `spoken`: asked by voice, so the answer is short and meant to be heard.
   *  `quiet`: the caller speaks the answer itself (voice mode). Resolves to the answer text. */
  async function send(text?: string, spoken = false, quiet = false): Promise<string | null> {
    const q = (text ?? input).trim();
    if (!q || !repoId || (thinking && !quiet)) return null;
    if (!quiet) setInput("");
    const past = history.current.slice(-6).map((m) => ({ role: m.role, text: m.text.slice(0, 600) }));
    setMessages((prev) => [...prev, { id: uid(), role: "user", text: q, voice: spoken || undefined }]);
    setThinking(true);
    try {
      const r = await api.ask(repoId, q, past, spoken);
      const id = uid();
      setMessages((prev) => [...prev, { id, role: "sherpa", text: r.answer_markdown, meta: r }]);
      if (!quiet && (spoken || speakAnswers)) say(id, r.answer_markdown).catch(() => {});
      return r.answer_markdown;
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Request failed");
      setMessages((prev) => [
        ...prev,
        { id: uid(), role: "sherpa", text: "Sorry, I couldn't answer that. The error is shown in the corner; please try again." },
      ]);
      return null;
    } finally {
      setThinking(false);
    }
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {(chats.length > 0 || messages.length > 0) && (
        <div className="flex items-center gap-1 border-b border-border px-3 py-1.5">
          <Menu.Root>
            <Menu.Trigger className="inline-flex h-8 max-w-[60%] items-center gap-1.5 rounded-md px-2 text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground data-[popup-open]:bg-secondary">
              <History className="size-3.5" />
              <span className="truncate">
                {messages.length ? chats.find((c) => c.id === chatId)?.title || "This chat" : "Recent chats"}
              </span>
              <ChevronDown className="size-3" />
            </Menu.Trigger>
            <Menu.Popup className="max-h-[60vh] w-80 overflow-y-auto">
              <Menu.Label>Saved on this device</Menu.Label>
              {chats.length === 0 && <p className="px-2.5 py-2 text-xs text-muted-foreground">No saved chats yet.</p>}
              {chats.slice(0, 50).map((c) => (
                <Menu.Item key={c.id} onClick={() => openChat(c)} className={cn(c.id === chatId && "bg-secondary/60")}>
                  <span className="min-w-0 flex-1 truncate">{c.title}</span>
                  <span className="shrink-0 text-[11px] text-muted-foreground">{timeAgo(c.updatedAt / 1000)}</span>
                </Menu.Item>
              ))}
              {messages.length > 0 && chats.some((c) => c.id === chatId) && (
                <>
                  <Menu.Separator />
                  <Menu.Item onClick={() => removeChat(chatId)} className="text-destructive">
                    <Trash2 className="!text-destructive" /> Delete this chat
                  </Menu.Item>
                </>
              )}
            </Menu.Popup>
          </Menu.Root>
          <Button variant="ghost" size="sm" onClick={newChat} disabled={!messages.length} className="ml-auto h-8 gap-1.5 px-2 text-xs">
            <SquarePen className="size-3.5" /> New chat
          </Button>
        </div>
      )}
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
          {canListen && (
            <Button
              size="icon-sm"
              variant={listening ? "default" : "ghost"}
              onClick={talk}
              disabled={!repoId || thinking}
              className={cn("shrink-0 rounded-lg", listening && "motion-safe:animate-pulse")}
              aria-label={listening ? "Stop listening" : "Ask by voice"}
              aria-pressed={listening}
              title={listening ? "Listening… click to stop" : "Ask by voice; Sherpa answers out loud"}
            >
              <Mic className="size-4" />
            </Button>
          )}
          {canConverse && (
            <Button
              size="icon-sm"
              variant="ghost"
              onClick={() => setVoiceMode(true)}
              disabled={!repoId}
              className="shrink-0 rounded-lg"
              aria-label="Voice conversation"
              title="Voice conversation: talk with Sherpa hands-free"
            >
              <AudioLines className="size-4" />
            </Button>
          )}
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
        <div className="mx-auto mt-1.5 flex max-w-3xl items-center justify-between gap-3 text-[11px] text-muted-foreground">
          <p className="hidden sm:block">Enter to send · Shift+Enter for a new line · follow-ups keep context</p>
          <button
            type="button"
            onClick={toggleSpeakAnswers}
            aria-pressed={speakAnswers}
            className={cn(
              "ml-auto inline-flex items-center gap-1 transition-colors",
              speakAnswers ? "text-primary" : "hover:text-foreground"
            )}
          >
            {speakAnswers ? <Volume2 className="size-3.5" /> : <VolumeX className="size-3.5" />}
            Speak answers {speakAnswers ? "on" : "off"}
          </button>
        </div>
      </div>
      <AnimatePresence>
        {voiceMode && (
          <VoiceMode repoId={repoId} repoName={repoName} ask={(q) => send(q, true, true)} onClose={() => setVoiceMode(false)} />
        )}
      </AnimatePresence>
    </div>
  );
}
