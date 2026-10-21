// Render an ad to MP4: step the page frame by frame in headless Chrome, add a Polly voiceover.
// usage: node render.mjs <ad.html> <out.mp4> [voice=Ruth] [fps=30]; frame size = the page's #stage
import { spawn, execFileSync } from "node:child_process";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const [, , page, out, voice = "Ruth", fpsArg = "30"] = process.argv;
const fps = Number(fpsArg);
const work = join(here, ".render", basename(page, ".html"));
rmSync(work, { recursive: true, force: true });
mkdirSync(join(work, "frames"), { recursive: true });

const port = 9400 + Math.floor(Math.random() * 400);
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", [
  "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
  `--remote-debugging-port=${port}`, `--user-data-dir=${join(work, "chrome")}`, "about:blank",
], { stdio: "ignore" });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

try {
  let target;
  for (let i = 0; i < 40 && !target; i++) {
    await wait(250);
    target = await fetch(`http://127.0.0.1:${port}/json/list`).then((r) => r.json()).then((l) => l.find((t) => t.type === "page")).catch(() => null);
  }
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r) => (ws.onopen = r));
  let id = 0;
  const pending = new Map();
  ws.onmessage = (m) => {
    const d = JSON.parse(m.data);
    if (pending.has(d.id)) pending.get(d.id)(d), pending.delete(d.id);
  };
  const send = (method, params = {}) => new Promise((r) => { pending.set(++id, r); ws.send(JSON.stringify({ id, method, params })); });
  const js = async (expression) => (await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true })).result?.result?.value;

  await send("Emulation.setDeviceMetricsOverride", { width: 1080, height: 1920, deviceScaleFactor: 1, mobile: false });
  await send("Page.enable");
  await send("Page.navigate", { url: "file://" + resolve(here, page) + "?still" });
  for (let i = 0; i < 80 && !(await js("!!window.ready")); i++) await wait(100);
  await js("window.ready");
  await wait(400);
  // frame size comes from the ad's stage (1080×1920 vertical, 1920×1080 horizontal)
  const size = await js("JSON.stringify([document.getElementById('stage').offsetWidth, document.getElementById('stage').offsetHeight])").then(JSON.parse);
  await send("Emulation.setDeviceMetricsOverride", { width: size[0], height: size[1], deviceScaleFactor: 1, mobile: false });
  await wait(200);
  const duration = await js("window.DURATION");
  const script = await js("window.SCRIPT");
  const box = await js("JSON.stringify(document.getElementById('stage').getBoundingClientRect())").then(JSON.parse);
  const clip = { x: box.x, y: box.y, width: size[0], height: size[1], scale: 1 };

  // STILLS=3,12.5 → just those moments as PNGs next to the output (for checking a layout), plus the voice timing
  if (process.env.STILLS) {
    for (const s of process.env.STILLS.split(",").map(Number)) {
      await js(`window.render(${s})`);
      const shot = await send("Page.captureScreenshot", { format: "png", clip });
      writeFileSync(`${resolve(out)}-${s}s.png`, Buffer.from(shot.result.data, "base64"));
    }
    writeFileSync(join(work, "script.json"), JSON.stringify(script));
    execFileSync("python3.11", [join(here, "vo.py"), join(work, "script.json"), voice, join(work, "vo")], { stdio: "inherit" });
    process.exit(0);
  }

  const frames = Math.round(duration * fps);
  for (let f = 0; f < frames; f++) {
    await js(`window.render(${f / fps})`);
    const shot = await send("Page.captureScreenshot", { format: "jpeg", quality: 92, clip });
    writeFileSync(join(work, "frames", `f${String(f).padStart(4, "0")}.jpg`), Buffer.from(shot.result.data, "base64"));
    if (f % 150 === 0) console.log(`frame ${f}/${frames}`);
  }
  ws.close();

  // voiceover: one clip per subtitle line, placed at its start time
  writeFileSync(join(work, "script.json"), JSON.stringify(script));
  execFileSync("python3.11", [join(here, "vo.py"), join(work, "script.json"), voice, join(work, "vo")], { stdio: "inherit" });
  const inputs = script.flatMap((_, i) => ["-i", join(work, "vo", `vo${i}.mp3`)]);
  const delays = script.map((l, i) => `[${i + 1}:a]adelay=${Math.round(l.a * 1000)}|${Math.round(l.a * 1000)}[v${i}]`).join(";");
  const mix = script.map((_, i) => `[v${i}]`).join("") + `amix=inputs=${script.length}:normalize=0,apad,atrim=0:${duration},loudnorm=I=-16:TP=-1.5[aout]`;
  execFileSync("ffmpeg", [
    "-y", "-loglevel", "error", "-framerate", String(fps), "-i", join(work, "frames", "f%04d.jpg"), ...inputs,
    "-filter_complex", `${delays};${mix}`, "-map", "0:v", "-map", "[aout]",
    "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
    "-c:a", "aac", "-b:a", "192k", "-t", String(duration), resolve(out),
  ], { stdio: "inherit" });
  console.log("wrote", resolve(out));
} finally {
  chrome.kill();
}
