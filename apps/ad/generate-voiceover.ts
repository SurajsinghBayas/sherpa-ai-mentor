/**
 * Sherpa Ad — ElevenLabs voiceover generator
 *
 * Usage:
 *   ELEVENLABS_API_KEY=your_key npx tsx generate-voiceover.ts
 *
 * Output: public/vo/s1.mp3 … s6.mp3
 *
 * To wire into Remotion, import Audio + staticFile in SherpaAd.tsx:
 *
 *   import { Audio } from "remotion";
 *   import { staticFile } from "remotion";
 *
 *   // Inside each Sequence (adjust startFrom to sync with animation):
 *   <Audio src={staticFile("vo/s1.mp3")} startFrom={45} />
 *
 * Scene timings (30fps):
 *   s1  0–150   (0–5s)    "Meet Sherpa."
 *   s2  150–300 (5–10s)   codebase problem
 *   s3  300–450 (10–15s)  "Just ask."
 *   s4  450–690 (15–23s)  grounded answer
 *   s5  690–810 (23–27s)  feature beats
 *   s6  810–900 (27–30s)  CTA
 */

import fs from "fs";
import path from "path";

const API_KEY = process.env.ELEVENLABS_API_KEY;
if (!API_KEY) {
  console.error("Set ELEVENLABS_API_KEY env var before running.");
  process.exit(1);
}

// Liam — calm, measured, American male. Ideal for cinematic tech ads.
// Alternatives: "Adam" pNInz6obpgDQGcFmaJgB, "Josh" TxGEqnHWrfWFTfGW9XjX
const VOICE_ID = "TX3LPaxmHKxFdv7VOQHJ";
const MODEL_ID = "eleven_turbo_v2_5"; // fastest + highest quality

// Voice settings tuned for a clean, confident delivery — not over-polished.
const VOICE_SETTINGS = {
  stability: 0.72,
  similarity_boost: 0.76,
  style: 0.34,
  use_speaker_boost: true,
};

interface Segment {
  id: string;
  text: string;
  sceneLabel: string;
  startFrame: number;  // for documentation / sync reference
}

const SEGMENTS: Segment[] = [
  {
    id: "s1",
    sceneLabel: "Intro",
    startFrame: 45,   // orb is fully in by frame 45
    text: "Meet Sherpa.",
  },
  {
    id: "s2",
    sceneLabel: "Problem",
    startFrame: 155,
    text:
      "Every new codebase is unfamiliar territory. " +
      "Hundreds of files. No map. No guide.",
  },
  {
    id: "s3",
    sceneLabel: "Ask",
    startFrame: 310,
    text: "Just ask.",
  },
  {
    id: "s4",
    sceneLabel: "Answer",
    startFrame: 452,
    text:
      "Sherpa reads every file, every function, every line. " +
      "And answers with exact proof — file and line, every time.",
  },
  {
    id: "s5",
    sceneLabel: "Features",
    startFrame: 692,
    text: "Architecture maps. Guided tours. Starter tasks.",
  },
  {
    id: "s6",
    sceneLabel: "CTA",
    startFrame: 812,
    text: "Any repo. No setup required.",
  },
];

const OUT_DIR = path.join(__dirname, "public", "vo");

async function generate(seg: Segment): Promise<void> {
  console.log(`  → Scene ${seg.id} (${seg.sceneLabel}): "${seg.text}"`);

  const res = await fetch(
    `https://api.elevenlabs.io/v1/text-to-speech/${VOICE_ID}`,
    {
      method: "POST",
      headers: {
        "xi-api-key": API_KEY!,
        "Content-Type": "application/json",
        Accept: "audio/mpeg",
      },
      body: JSON.stringify({
        text: seg.text,
        model_id: MODEL_ID,
        voice_settings: VOICE_SETTINGS,
      }),
    },
  );

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`ElevenLabs ${res.status}: ${body}`);
  }

  const buf = Buffer.from(await res.arrayBuffer());
  const dest = path.join(OUT_DIR, `${seg.id}.mp3`);
  fs.writeFileSync(dest, buf);
  console.log(`  ✓ Saved ${dest} (${(buf.length / 1024).toFixed(0)} KB)`);
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });

  console.log("Generating Sherpa Ad voiceover via ElevenLabs…\n");
  console.log(`Voice: ${VOICE_ID} (Liam)`);
  console.log(`Model: ${MODEL_ID}`);
  console.log(`Output: ${OUT_DIR}\n`);

  for (const seg of SEGMENTS) {
    await generate(seg);
  }

  console.log("\nAll segments generated.");
  console.log("\nNext steps:");
  console.log("  1. Add <Audio> components to SherpaAd.tsx (see header comment)");
  console.log("  2. npm run render  →  out/sherpa-ad.mp4 with voiceover");
  console.log("\nSync tip: pass startFrom={Math.round(seg.startFrame)} to each");
  console.log("  <Audio> so the VO aligns with the animation beat.\n");

  // Print sync reference table
  console.log("Sync reference:");
  console.log("  Scene  | startFrom  | Text preview");
  console.log("  -------+------------+----------------------------");
  for (const seg of SEGMENTS) {
    const preview = seg.text.slice(0, 36) + (seg.text.length > 36 ? "…" : "");
    console.log(`  ${seg.id.padEnd(6)} | ${String(seg.startFrame).padEnd(10)} | ${preview}`);
  }
}

main().catch((err) => {
  console.error("Error:", err.message);
  process.exit(1);
});
