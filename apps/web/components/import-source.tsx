"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { AlertCircle, FileArchive, FolderOpen, Github, Loader2, RotateCcw, Terminal, Upload, X } from "lucide-react";
import { api, ApiError, type UploadJob } from "../lib/api";
import { formatBytes, planFolder, zipFolder, type FolderPlan } from "../lib/source-filter";
import { cn } from "../lib/utils";
import NumberFlow from "@number-flow/react";
import { CliQuickstart } from "./cli-guide";
import { Sherpa } from "./sherpa";
import { Badge, Button, Input, Tabs } from "./ui/primitives";

type Source = "github" | "zip" | "folder" | "cli";
type Phase =
  | { kind: "pick" }
  | { kind: "planned"; plan: FolderPlan } // folder chosen: local summary before anything is sent
  | { kind: "sending"; percent: number; label: string } // pack (folder) + upload + server check: one bar
  | { kind: "job"; job: UploadJob };

const DEMO_REPO = "https://github.com/fastapi/full-stack-fastapi-template";
const STAGE_LABEL: Record<string, string> = {
  queued: "Waiting for a worker", reading: "Reading files", chunking: "Splitting code into chunks",
  saving: "Saving chunks", embedding: "Embedding chunks", done: "Done", failed: "Failed",
};
const SKIP_LABEL: Record<string, string> = {
  generated: "generated / dependencies", secret: "secrets (.env, keys)", binary: "binary / media",
  "too large": "over 400 KB", "unsafe path": "unsafe paths", symlink: "symlinks", encrypted: "encrypted",
  empty: "empty", unreadable: "unreadable", "over limit": "over the size limit",
};

const SOURCES: { id: Source; icon: typeof Github; label: string }[] = [
  { id: "github", icon: Github, label: "GitHub" },
  { id: "zip", icon: FileArchive, label: "Upload ZIP" },
  { id: "folder", icon: FolderOpen, label: "Local folder" },
  { id: "cli", icon: Terminal, label: "CLI" },
];

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="eyebrow">{label}</p>
      <div className="mt-1 truncate text-sm font-medium tabular-nums">{value}</div>
    </div>
  );
}

/** Progress that only moves forward: late or out-of-order updates never pull it back.
 *  Give each separate action its own `track` so a new one starts from zero. */
function useForward(value: number, track: string) {
  const best = useRef({ track, value: 0 });
  if (best.current.track !== track) best.current = { track, value: 0 };
  best.current.value = Math.max(best.current.value, Math.min(100, Math.max(0, value)));
  return best.current.value;
}

function Bar({ value }: { value: number }) {
  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(value)}
      className="h-1.5 w-full overflow-hidden rounded-full bg-secondary"
    >
      <div
        className="h-full w-full origin-left rounded-full bg-primary transition-transform duration-500 ease-out"
        style={{ transform: `scaleX(${Math.max(2, value) / 100})` }}
      />
    </div>
  );
}

function Progress({ value, track, label, right, spinning }: {
  value: number; track: string; label: React.ReactNode; right?: React.ReactNode; spinning?: boolean;
}) {
  const v = useForward(value, track);
  return (
    <div className="min-w-0 flex-1 space-y-2">
      <div className="flex items-center justify-between gap-3 text-xs">
        <span className="flex min-w-0 items-center gap-1.5 truncate">
          {spinning && <Loader2 className="size-3.5 shrink-0 animate-spin text-muted-foreground" />} {label}
        </span>
        <span className="shrink-0 font-medium tabular-nums text-muted-foreground">
          {right ?? <NumberFlow value={Math.round(v)} suffix="%" />}
        </span>
      </div>
      <Bar value={v} />
    </div>
  );
}

export function ImportSource({
  localAllowed,
  onIndexed,
  onCancel,
}: {
  localAllowed: boolean;
  onIndexed: (repoId: string) => void;
  onCancel?: () => void;
}) {
  const [source, setSource] = useState<Source>("github");
  const [url, setUrl] = useState(onCancel ? "" : DEMO_REPO);
  const [cloning, setCloning] = useState(false);
  const [phase, setPhase] = useState<Phase>({ kind: "pick" });
  const [name, setName] = useState("");
  const [dragging, setDragging] = useState(false);
  const zipInput = useRef<HTMLInputElement>(null);
  const dirInput = useRef<HTMLInputElement>(null);

  // React has no prop for webkitdirectory; set it on the element
  useEffect(() => {
    dirInput.current?.setAttribute("webkitdirectory", "");
    dirInput.current?.setAttribute("directory", "");
  }, [source]);

  // pick up an upload that is still indexing (page reload, another tab, the CLI)
  useEffect(() => {
    api.uploads().then(({ uploads }) => {
      const live = uploads.find((u) => u.status === "queued" || u.status === "processing");
      if (live) {
        setSource(live.origin === "folder" ? "folder" : live.origin === "cli" ? "cli" : "zip");
        setPhase({ kind: "job", job: live });
      }
    }).catch(() => {});
  }, []);

  const job = phase.kind === "job" ? phase.job : null;

  // CLI tab: an upload started in the terminal shows up here as soon as it starts indexing
  useEffect(() => {
    if (source !== "cli" || phase.kind !== "pick") return;
    const since = Date.now() / 1000 - 5;
    const t = window.setInterval(async () => {
      try {
        const { uploads } = await api.uploads();
        const live = uploads.find(
          (u) => u.origin === "cli" && u.updated_at >= since && (u.status === "queued" || u.status === "processing")
        );
        if (live) setPhase({ kind: "job", job: live });
      } catch {
        /* keep watching */
      }
    }, 3000);
    return () => window.clearInterval(t);
  }, [source, phase.kind]);
  const running = job && (job.status === "queued" || job.status === "processing");

  // poll a running job
  useEffect(() => {
    if (!job || !running) return;
    const id = job.job_id;
    const t = window.setInterval(async () => {
      try {
        const j = await api.upload(id);
        setPhase({ kind: "job", job: j });
        if (j.status === "ready") {
          toast.success(`Indexed ${j.name}: ${j.detail}`);
          onIndexed(j.repo_id);
        } else if (j.status === "failed") {
          toast.error(`Indexing ${j.name} failed: ${j.detail}`);
        }
      } catch {
        /* transient; keep polling */
      }
    }, 1200);
    return () => window.clearInterval(t);
  }, [job?.job_id, running, onIndexed]); // eslint-disable-line react-hooks/exhaustive-deps

  const reset = useCallback(() => {
    setPhase({ kind: "pick" });
    setName("");
    if (zipInput.current) zipInput.current.value = "";
    if (dirInput.current) dirInput.current.value = "";
  }, []);

  async function cloneGithub() {
    const s = url.trim();
    if (!s) return;
    setCloning(true);
    try {
      const isUrl = /^https?:\/\//.test(s);
      const r = await api.ingest(isUrl ? { repo_url: s } : { local_path: s });
      const n = (r.changes.added?.length || 0) + (r.changes.modified?.length || 0) + (r.changes.removed?.length || 0);
      toast.success(`Indexed ${r.name}: ${r.files} files${n ? ` · ${n} changed since last index` : ""}`);
      setUrl("");
      onIndexed(r.repo_id);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Indexing failed");
    } finally {
      setCloning(false);
    }
  }

  /** Upload is the 30–90 % (folder) or 0–90 % (zip) slice; the server's file check fills the rest. */
  async function send(zip: Blob, filename: string, origin: "zip" | "folder", projectName: string) {
    const [from, to] = origin === "folder" ? [30, 90] : [0, 90];
    setPhase({ kind: "sending", percent: from, label: "Uploading" });
    try {
      const j = await api.uploadZip(zip, filename, projectName, origin, (f) =>
        setPhase(
          f >= 1
            ? { kind: "sending", percent: to, label: "Checking files on the server" }
            : { kind: "sending", percent: from + (to - from) * f, label: `Uploading ${formatBytes(zip.size)}` }
        )
      );
      setName(j.name);
      setPhase({ kind: "job", job: j });
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Upload failed");
      reset();
    }
  }

  function chooseZip(file: File | undefined) {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".zip")) {
      toast.error("Choose a .zip file");
      return;
    }
    send(file, file.name, "zip", "");
  }

  function chooseFolder(list: FileList | null) {
    if (!list || !list.length) return;
    const plan = planFolder(list);
    if (!plan.files.length) {
      toast.error("No source files in that folder (everything was dependencies, build output or binaries)");
      reset();
      return;
    }
    setName(plan.name);
    setPhase({ kind: "planned", plan });
  }

  async function uploadFolder(plan: FolderPlan) {
    setPhase({ kind: "sending", percent: 0, label: "Packing files" });
    try {
      const zip = await zipFolder(plan, (f) => setPhase({ kind: "sending", percent: 30 * f, label: "Packing files" }));
      setPhase({ kind: "sending", percent: 30, label: "Uploading" });
      await send(zip, `${name || plan.name}.zip`, "folder", name.trim() || plan.name);
    } catch {
      toast.error("Couldn't read the folder; try zipping it yourself and use Upload ZIP");
      reset();
    }
  }

  async function start(j: UploadJob) {
    try {
      setPhase({ kind: "job", job: await api.startUpload(j.job_id) });
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Couldn't start indexing");
    }
  }

  async function discard(j: UploadJob) {
    await api.discardUpload(j.job_id).catch(() => {});
    reset();
  }

  const busy = phase.kind === "sending" || !!running;

  return (
    <section aria-label="Add a repository" className="mx-auto max-w-3xl pt-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="mr-auto">
          <h2 className="text-[15px] font-semibold">Add a repository</h2>
          <p className="text-xs text-muted-foreground">Bring code from GitHub, a ZIP, a folder on this device, or the CLI.</p>
        </div>
        {onCancel && !busy && (
          <Button variant="ghost" size="icon-sm" onClick={onCancel} aria-label="Close">
            <X />
          </Button>
        )}
      </div>
      <Tabs
        label="Source"
        className="mt-3 w-fit max-w-full"
        value={source}
        onValueChange={(v) => {
          if (busy) return;
          setSource(v as Source);
          if (phase.kind !== "job" || job?.status === "ready") reset();
        }}
        tabs={SOURCES.map(({ id, icon: Icon, label }) => ({ value: id, label, icon: <Icon /> }))}
      />

      {source === "github" && (
        <div className="mt-3 flex gap-2">
          <Input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder={localAllowed ? "https://github.com/org/repo  or  /path/on/the/server" : "https://github.com/org/repo"}
            className="flex-1 font-mono text-xs"
            onKeyDown={(e) => e.key === "Enter" && !cloning && cloneGithub()}
            autoFocus
          />
          <Button onClick={cloneGithub} disabled={cloning || !url.trim()} className="shrink-0">
            {cloning ? (
              <>
                <Loader2 className="animate-spin" /> Indexing
              </>
            ) : (
              "Index repository"
            )}
          </Button>
        </div>
      )}
      {source === "github" && cloning && (
        <div className="mt-3 flex items-center gap-3 text-xs text-muted-foreground" role="status">
          <Sherpa pose="walking" size={48} decorative />
          Cloning and reading the repository. A mid-sized project takes about a minute.
        </div>
      )}

      {source === "cli" && phase.kind === "pick" && <CliQuickstart />}

      {(source === "zip" || source === "folder") && phase.kind === "pick" && (
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            if (source === "zip") chooseZip(e.dataTransfer.files[0]);
          }}
          onClick={() => (source === "zip" ? zipInput : dirInput).current?.click()}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), (source === "zip" ? zipInput : dirInput).current?.click())}
          role="button"
          tabIndex={0}
          className={cn(
            "mt-3 flex cursor-pointer flex-col items-center gap-1.5 rounded-lg border border-dashed border-input bg-background px-4 py-7 text-center transition-colors hover:border-primary/50 hover:bg-primary/[0.03]",
            dragging && "border-primary bg-primary/[0.06]"
          )}
        >
          <Upload className="size-5 text-muted-foreground" />
          <p className="text-sm font-medium">{source === "zip" ? "Drop a .zip here, or click to choose" : "Choose a folder on this device"}</p>
          <p className="text-[11px] text-muted-foreground">
            {source === "zip"
              ? "Up to 100 MB. node_modules, .git, build output, secrets and binaries are skipped."
              : "Dependencies, .git, build output, secrets and binaries stay on your machine; only source is uploaded."}
          </p>
          <input ref={zipInput} type="file" accept=".zip,application/zip" hidden onChange={(e) => chooseZip(e.target.files?.[0])} />
          <input ref={dirInput} type="file" multiple hidden onChange={(e) => chooseFolder(e.target.files)} />
        </div>
      )}

      {phase.kind === "planned" && (
        <div className="mt-3 space-y-3">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Project" value={<Input aria-label="Project name" value={name} onChange={(e) => setName(e.target.value)} className="h-7 text-sm" />} />
            <Stat label="Files to upload" value={phase.plan.files.length.toLocaleString()} />
            <Stat label="Size" value={formatBytes(phase.plan.totalBytes)} />
            <Stat label="Type" value={phase.plan.projectTypes.join(", ") || "—"} />
          </div>
          {Object.keys(phase.plan.skipped).length > 0 && (
            <p className="text-[11px] text-muted-foreground">
              Staying on your machine:{" "}
              {Object.entries(phase.plan.skipped).map(([k, v]) => `${v!.toLocaleString()} ${SKIP_LABEL[k] || k}`).join(" · ")}
              {phase.plan.skippedDirs.length > 0 && <> ({phase.plan.skippedDirs.join(", ")})</>}
            </p>
          )}
          <div className="flex gap-2">
            <Button size="sm" onClick={() => uploadFolder(phase.plan)} disabled={!name.trim()}>
              <Upload className="size-3.5" /> Upload {phase.plan.files.length.toLocaleString()} files
            </Button>
            <Button size="sm" variant="ghost" onClick={reset}>Choose another</Button>
          </div>
        </div>
      )}

      {phase.kind === "sending" && (
        <div className="mt-3 flex items-center gap-3">
          <Sherpa pose="walking" size={48} decorative />
          <Progress value={phase.percent} track="send" label={phase.label} spinning />
        </div>
      )}

      {job && job.status === "review" && job.manifest && (
        <div className="mt-3 space-y-3">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Project" value={job.name} />
            <Stat label="Files" value={job.manifest.file_count.toLocaleString()} />
            <Stat label="Size" value={formatBytes(job.manifest.total_bytes)} />
            <Stat label="Type" value={job.manifest.project_types.join(", ") || "—"} />
          </div>
          <div className="flex flex-wrap gap-1.5">
            {job.manifest.languages.slice(0, 8).map((l) => (
              <Badge key={l.language} variant="secondary" className="font-normal">
                {l.language} <span className="text-muted-foreground">{l.files}</span>
              </Badge>
            ))}
          </div>
          {job.manifest.entry_points.length > 0 && (
            <p className="text-[11px] text-muted-foreground">
              Likely entry points: <span className="font-mono text-foreground/80">{job.manifest.entry_points.slice(0, 5).join(", ")}</span>
            </p>
          )}
          {job.manifest.skipped_count > 0 && (
            <p className="text-[11px] text-muted-foreground">
              Skipped {job.manifest.skipped_count.toLocaleString()}:{" "}
              {Object.entries(job.manifest.skipped).map(([k, v]) => `${v.toLocaleString()} ${SKIP_LABEL[k] || k}`).join(" · ")}
              {job.manifest.skipped_dirs.length > 0 && <> ({job.manifest.skipped_dirs.join(", ")})</>}
            </p>
          )}
          {job.manifest.truncated && (
            <p className="flex items-center gap-1.5 text-[11px] text-warning">
              <AlertCircle className="size-3" /> Large project: only the first files within the limit will be indexed.
            </p>
          )}
          {job.updates_existing && (
            <p className="text-[11px] text-muted-foreground">You've uploaded {job.name} before; only changed files will be re-indexed.</p>
          )}
          <div className="flex gap-2">
            <Button size="sm" onClick={() => start(job)}>Start indexing</Button>
            <Button size="sm" variant="ghost" onClick={() => discard(job)}>Discard</Button>
          </div>
        </div>
      )}

      {job && (running || job.status === "ready") && (
        <div className="mt-3 flex items-center gap-3">
          <Sherpa pose={running ? "walking" : "success"} size={48} decorative />
          <div className="min-w-0 flex-1 space-y-2">
          <Progress
            value={job.progress}
            track={`${job.job_id}:${job.attempts}`}
            spinning={!!running}
            label={<>{job.name} · {STAGE_LABEL[job.stage] || job.stage}{running && job.detail ? <span className="text-muted-foreground"> · {job.detail}</span> : null}</>}
          />
          {running && <p className="text-[11px] text-muted-foreground">You can keep working; indexing continues if you leave this page.</p>}
          </div>
        </div>
      )}

      {job && job.status === "failed" && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <p className="flex flex-1 items-center gap-1.5 text-xs text-destructive"><AlertCircle className="size-3.5" /> {job.detail}</p>
          {job.can_retry && (
            <Button size="sm" variant="outline" onClick={() => start(job)}>
              <RotateCcw className="size-3.5" /> Retry
            </Button>
          )}
          <Button size="sm" variant="ghost" onClick={() => discard(job)}>Dismiss</Button>
        </div>
      )}
    </section>
  );
}
