"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { KeyRound, Loader2, Plug, Trash2 } from "lucide-react";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Label, Separator } from "./ui/primitives";

const PROVIDERS = [
  { id: "openai", label: "OpenAI", hint: "sk-…", models: ["gpt-4o-mini", "gpt-4o"] },
  { id: "anthropic", label: "Anthropic", hint: "sk-ant-…", models: ["claude-3-5-haiku-latest", "claude-3-5-sonnet-latest"] },
  { id: "gemini", label: "Google Gemini", hint: "AI…", models: ["gemini-1.5-flash", "gemini-1.5-pro"] },
  { id: "openrouter", label: "OpenRouter", hint: "sk-or-…", models: ["openai/gpt-4o-mini", "anthropic/claude-3.5-haiku", "google/gemini-flash-1.5", "meta-llama/llama-3.1-70b-instruct"] },
];

export function Settings() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [keys, setKeys] = useState<any[]>([]);
  const [endpoints, setEndpoints] = useState<any[]>([]);
  const [provider, setProvider] = useState("openai");
  const [label, setLabel] = useState("");
  const [model, setModel] = useState("gpt-4o-mini");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
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
  useEffect(() => { if (user) refresh(); }, [user]);

  if (loading || !user) return <main className="container py-10">Loading…</main>;

  async function addKey(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.addKey(label || provider, provider, model, apiKey);
      toast.success("Key saved — encrypted at rest");
      setApiKey(""); setLabel(""); refresh();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function addEndpoint(e: React.FormEvent) {
    e.preventDefault();
    setEpBusy(true);
    try {
      await api.addEndpoint(epName || epUrl, epUrl, epKind, epModel || "default", epKey);
      toast.success("Endpoint saved");
      setEpName(""); setEpUrl(""); setEpKey(""); setEpModel(""); refresh();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Save failed");
    } finally {
      setEpBusy(false);
    }
  }

  async function testNow() {
    if (!epUrl.trim()) return toast.error("Enter a base URL first");
    setTesting(true);
    try {
      const r = await api.testEndpoint(epName, epUrl, epKind);
      r.ok ? toast.success(`Reachable (HTTP ${r.status ?? "?"})`) : toast.error(r.hint);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Probe failed");
    } finally {
      setTesting(false);
    }
  }

  return (
    <main className="container max-w-3xl space-y-6 py-8">
      <div className="animate-fade-up">
        <h1 className="text-2xl font-semibold tracking-tight">Keys & endpoints</h1>
        <p className="text-sm text-muted-foreground">Your credentials unlock hosted models. Stored Fernet-encrypted — the UI only ever shows last4.</p>
      </div>

      <Card className="animate-fade-up">
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><KeyRound className="size-4" /> Provider keys</CardTitle>
          <CardDescription>OpenAI, Anthropic, Gemini, or OpenRouter. Pick one per answer in the Mentor.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {keys.length > 0 && (
            <ul className="space-y-2">
              {keys.map((k) => (
                <li key={k.id} className="flex items-center gap-3 rounded-lg border px-3 py-2 text-sm">
                  <Badge variant="secondary">{k.provider}</Badge>
                  <span className="font-medium">{k.label}</span>
                  <span className="font-mono text-xs text-muted-foreground">{k.model} · {k.last4}</span>
                  <Button variant="ghost" size="sm" className="ml-auto"
                    onClick={() => api.deleteKey(k.id).then(() => { toast.success("Key deleted"); refresh(); }).catch(() => toast.error("Delete failed"))}>
                    <Trash2 /> Delete
                  </Button>
                </li>
              ))}
            </ul>
          )}
          <Separator />
          <form onSubmit={addKey} className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5"><Label>Provider</Label>
              <select value={provider} onChange={(e) => { setProvider(e.target.value); setModel(PROVIDERS.find((p) => p.id === e.target.value)!.models[0]); }}
                className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm">
                {PROVIDERS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
              </select></div>
            <div className="space-y-1.5"><Label>Label</Label>
              <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="personal" /></div>
            <div className="space-y-1.5"><Label>Model</Label>
              <Input value={model} onChange={(e) => setModel(e.target.value)} className="font-mono" /></div>
            <div className="space-y-1.5"><Label>API key ({PROVIDERS.find((p) => p.id === provider)!.hint})</Label>
              <Input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} required /></div>
            <div className="sm:col-span-2"><Button disabled={busy} className="w-full">{busy && <Loader2 className="animate-spin" />} Save key</Button></div>
          </form>
        </CardContent>
      </Card>

      <Card className="animate-fade-up">
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Plug className="size-4" /> Custom endpoints</CardTitle>
          <CardDescription>Any OpenAI-compatible gateway (vLLM, LiteLLM, Cloudflare AI Gateway…) or Ollama. Test before saving.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {endpoints.length > 0 && (
            <ul className="space-y-2">
              {endpoints.map((e) => (
                <li key={e.id} className="flex items-center gap-3 rounded-lg border px-3 py-2 text-sm">
                  <Badge variant="outline">{e.kind}</Badge>
                  <span className="font-medium">{e.name}</span>
                  <span className="truncate font-mono text-xs text-muted-foreground">{e.base_url}</span>
                  <Button variant="ghost" size="sm" className="ml-auto"
                    onClick={() => api.deleteEndpoint(e.id).then(() => { toast.success("Endpoint deleted"); refresh(); }).catch(() => toast.error("Delete failed"))}>
                    <Trash2 /> Delete
                  </Button>
                </li>
              ))}
            </ul>
          )}
          <Separator />
          <form onSubmit={addEndpoint} className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5"><Label>Name</Label>
              <Input value={epName} onChange={(e) => setEpName(e.target.value)} placeholder="team gateway" /></div>
            <div className="space-y-1.5"><Label>Kind</Label>
              <select value={epKind} onChange={(e) => setEpKind(e.target.value)}
                className="h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm">
                <option value="openai-compatible">OpenAI-compatible</option>
                <option value="ollama">Ollama</option>
              </select></div>
            <div className="space-y-1.5 sm:col-span-2"><Label>Base URL</Label>
              <Input value={epUrl} onChange={(e) => setEpUrl(e.target.value)} placeholder="https://gateway.internal/v1" className="font-mono" required /></div>
            <div className="space-y-1.5"><Label>Model</Label>
              <Input value={epModel} onChange={(e) => setEpModel(e.target.value)} placeholder="llama-3.1-70b" className="font-mono" /></div>
            <div className="space-y-1.5"><Label>API key (optional)</Label>
              <Input type="password" value={epKey} onChange={(e) => setEpKey(e.target.value)} placeholder="Ollama needs none" /></div>
            <div className="flex gap-2 sm:col-span-2">
              <Button type="button" variant="outline" onClick={testNow} disabled={testing} className="flex-1">
                {testing && <Loader2 className="animate-spin" />} Test connection</Button>
              <Button disabled={epBusy} className="flex-1">{epBusy && <Loader2 className="animate-spin" />} Save endpoint</Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
