"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { toast } from "sonner";
import {
  CheckCircle2,
  KeyRound,
  Loader2,
  Plug,
  Plus,
  Trash2,
} from "lucide-react";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import {
  Badge,
  Button,
  Input,
  Label,
  Select,
  Separator,
} from "./ui/primitives";

const ease = [0.22, 1, 0.36, 1] as const;

const PROVIDERS = [
  { id: "openai", label: "OpenAI", hint: "sk-…", models: ["gpt-4o-mini", "gpt-4o"] },
  {
    id: "anthropic",
    label: "Anthropic",
    hint: "sk-ant-…",
    models: ["claude-haiku-4-5-20251001", "claude-sonnet-4-6"],
  },
  {
    id: "gemini",
    label: "Google Gemini",
    hint: "AI…",
    models: ["gemini-2.0-flash", "gemini-2.0-pro"],
  },
  {
    id: "openrouter",
    label: "OpenRouter",
    hint: "sk-or-…",
    models: [
      "openai/gpt-4o-mini",
      "anthropic/claude-3.5-haiku",
      "google/gemini-flash-1.5",
      "meta-llama/llama-3.1-70b-instruct",
    ],
  },
];

function rise(i: number) {
  return {
    initial: { opacity: 0, y: 14 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.5, delay: i * 0.06, ease },
  };
}

export function Settings() {
  const { user, loading } = useAuth();
  const router = useRouter();

  const [keys, setKeys] = useState<any[]>([]);
  const [endpoints, setEndpoints] = useState<any[]>([]);

  /* key form */
  const [provider, setProvider] = useState("openai");
  const [label, setLabel] = useState("");
  const [model, setModel] = useState("gpt-4o-mini");
  const [apiKey, setApiKey] = useState("");
  const [keyBusy, setKeyBusy] = useState(false);

  /* endpoint form */
  const [epName, setEpName] = useState("");
  const [epUrl, setEpUrl] = useState("");
  const [epKind, setEpKind] = useState("openai-compatible");
  const [epModel, setEpModel] = useState("");
  const [epKey, setEpKey] = useState("");
  const [epBusy, setEpBusy] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);

  const refresh = () => {
    api.keys().then(setKeys).catch(() => {});
    api.endpoints().then(setEndpoints).catch(() => {});
  };
  useEffect(() => {
    if (user) refresh();
  }, [user]);

  if (loading || !user) {
    return (
      <main className="container flex h-[calc(100vh-3.5rem)] items-center justify-center">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </main>
    );
  }

  async function addKey(e: React.FormEvent) {
    e.preventDefault();
    setKeyBusy(true);
    try {
      await api.addKey(label || provider, provider, model, apiKey);
      toast.success("Key saved — encrypted at rest");
      setApiKey("");
      setLabel("");
      refresh();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Save failed");
    } finally {
      setKeyBusy(false);
    }
  }

  async function addEndpoint(e: React.FormEvent) {
    e.preventDefault();
    setEpBusy(true);
    try {
      await api.addEndpoint(epName || epUrl, epUrl, epKind, epModel || "default", epKey);
      toast.success("Endpoint saved");
      setEpName("");
      setEpUrl("");
      setEpKey("");
      setEpModel("");
      refresh();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Save failed");
    } finally {
      setEpBusy(false);
    }
  }

  async function testEndpoint() {
    if (!epUrl.trim()) return toast.error("Enter a base URL first");
    setTesting(true);
    try {
      const r = await api.testEndpoint(epName, epUrl, epKind);
      r.ok
        ? toast.success(`Reachable — HTTP ${r.status ?? "?"}`)
        : toast.error(r.hint);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Probe failed");
    } finally {
      setTesting(false);
    }
  }

  return (
    <main className="container max-w-2xl py-10 space-y-8">
      <motion.div {...rise(0)}>
        <h1 className="text-2xl font-semibold tracking-tight">Keys & endpoints</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Stored Fernet-encrypted. The UI only shows the last 4 characters of each key.
        </p>
      </motion.div>

      {/* ── Provider keys ── */}
      <motion.section {...rise(1)} className="rounded-2xl border border-border bg-card overflow-hidden">
        <div className="flex items-center gap-3 border-b border-border px-6 py-4">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary">
            <KeyRound className="size-4 text-foreground" />
          </span>
          <div>
            <h2 className="text-sm font-semibold">Provider keys</h2>
            <p className="text-xs text-muted-foreground">OpenAI, Anthropic, Gemini, or OpenRouter</p>
          </div>
        </div>

        <div className="p-6 space-y-5">
          {keys.length > 0 && (
            <>
              <ul className="space-y-2">
                {keys.map((k) => (
                  <motion.li
                    key={k.id}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    className="flex items-center gap-3 rounded-xl border border-border bg-secondary/30 px-4 py-3 text-sm"
                  >
                    <Badge variant="secondary" className="text-[10px]">{k.provider}</Badge>
                    <span className="font-medium">{k.label}</span>
                    <span className="font-mono text-xs text-muted-foreground">
                      {k.model} · ••••{k.last4}
                    </span>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="ml-auto text-muted-foreground hover:text-destructive"
                      onClick={() =>
                        api
                          .deleteKey(k.id)
                          .then(() => {
                            toast.success("Key deleted");
                            refresh();
                          })
                          .catch(() => toast.error("Delete failed"))
                      }
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </motion.li>
                ))}
              </ul>
              <Separator />
            </>
          )}

          <form onSubmit={addKey} className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Provider</Label>
              <Select
                value={provider}
                onChange={(e) => {
                  setProvider(e.target.value);
                  setModel(PROVIDERS.find((p) => p.id === e.target.value)!.models[0]);
                }}
              >
                {PROVIDERS.map((p) => (
                  <option key={p.id} value={p.id}>{p.label}</option>
                ))}
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label>Label <span className="text-muted-foreground font-normal">(optional)</span></Label>
              <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="personal" />
            </div>

            <div className="space-y-1.5">
              <Label>Model</Label>
              <Input
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="font-mono"
                list="model-suggestions"
              />
              <datalist id="model-suggestions">
                {PROVIDERS.find((p) => p.id === provider)?.models.map((m) => (
                  <option key={m} value={m} />
                ))}
              </datalist>
            </div>

            <div className="space-y-1.5">
              <Label>API key ({PROVIDERS.find((p) => p.id === provider)!.hint})</Label>
              <Input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="Paste key…"
                required
              />
            </div>

            <div className="sm:col-span-2">
              <Button disabled={keyBusy} className="w-full">
                {keyBusy ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Plus className="size-4" />
                )}
                {keyBusy ? "Saving…" : "Add key"}
              </Button>
            </div>
          </form>
        </div>
      </motion.section>

      {/* ── Custom endpoints ── */}
      <motion.section {...rise(2)} className="rounded-2xl border border-border bg-card overflow-hidden">
        <div className="flex items-center gap-3 border-b border-border px-6 py-4">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-secondary">
            <Plug className="size-4 text-foreground" />
          </span>
          <div>
            <h2 className="text-sm font-semibold">Custom endpoints</h2>
            <p className="text-xs text-muted-foreground">
              vLLM, LiteLLM, Ollama, or any OpenAI-compatible gateway
            </p>
          </div>
        </div>

        <div className="p-6 space-y-5">
          {endpoints.length > 0 && (
            <>
              <ul className="space-y-2">
                {endpoints.map((e) => (
                  <motion.li
                    key={e.id}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    className="flex items-center gap-3 rounded-xl border border-border bg-secondary/30 px-4 py-3 text-sm"
                  >
                    <Badge variant="outline" className="text-[10px] shrink-0">{e.kind}</Badge>
                    <span className="font-medium shrink-0">{e.name}</span>
                    <span className="min-w-0 truncate font-mono text-xs text-muted-foreground">
                      {e.base_url}
                    </span>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className="ml-auto shrink-0 text-muted-foreground hover:text-destructive"
                      onClick={() =>
                        api
                          .deleteEndpoint(e.id)
                          .then(() => {
                            toast.success("Endpoint deleted");
                            refresh();
                          })
                          .catch(() => toast.error("Delete failed"))
                      }
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </motion.li>
                ))}
              </ul>
              <Separator />
            </>
          )}

          <form onSubmit={addEndpoint} className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Name</Label>
              <Input value={epName} onChange={(e) => setEpName(e.target.value)} placeholder="team gateway" />
            </div>

            <div className="space-y-1.5">
              <Label>Kind</Label>
              <Select value={epKind} onChange={(e) => setEpKind(e.target.value)}>
                <option value="openai-compatible">OpenAI-compatible</option>
                <option value="ollama">Ollama</option>
              </Select>
            </div>

            <div className="space-y-1.5 sm:col-span-2">
              <Label>Base URL</Label>
              <Input
                value={epUrl}
                onChange={(e) => setEpUrl(e.target.value)}
                placeholder="https://gateway.internal/v1"
                className="font-mono"
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label>Model</Label>
              <Input
                value={epModel}
                onChange={(e) => setEpModel(e.target.value)}
                placeholder="llama-3.1-70b"
                className="font-mono"
              />
            </div>

            <div className="space-y-1.5">
              <Label>API key <span className="text-muted-foreground font-normal">(if required)</span></Label>
              <Input
                type="password"
                value={epKey}
                onChange={(e) => setEpKey(e.target.value)}
                placeholder="Ollama doesn't need one"
              />
            </div>

            <div className="flex gap-2 sm:col-span-2">
              <Button
                type="button"
                variant="outline"
                onClick={testEndpoint}
                disabled={testing}
                className="flex-1"
              >
                {testing ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="size-4" />
                )}
                Test connection
              </Button>
              <Button disabled={epBusy} className="flex-1">
                {epBusy ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
                {epBusy ? "Saving…" : "Add endpoint"}
              </Button>
            </div>
          </form>
        </div>
      </motion.section>
    </main>
  );
}
