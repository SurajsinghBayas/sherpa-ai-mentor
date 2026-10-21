"""Voiceover for an ad: one Amazon Polly clip per script line (keys come from the API's .env).

usage: python3.11 vo.py <script.json> <voice> <out_dir>
script.json = [{"a": start_s, "b": end_s, "text": "..."}]; prints each clip's duration.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "api"))
import boto3  # noqa: E402
from app.config import settings  # noqa: E402

script, voice, out = json.load(open(sys.argv[1])), sys.argv[2], Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
polly = boto3.client("polly", region_name=settings.polly_region or settings.aws_default_region,
                     aws_access_key_id=settings.polly_access_key_id or None,
                     aws_secret_access_key=settings.polly_secret_access_key or None)
for i, line in enumerate(script):
    f = out / f"vo{i}.mp3"
    r = polly.synthesize_speech(Text=line["text"], OutputFormat="mp3", VoiceId=voice, Engine="generative",
                                SampleRate="24000")
    f.write_bytes(r["AudioStream"].read())
    dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                         "-of", "csv=p=0", str(f)]).strip())
    room = line["b"] - line["a"]
    print(f"{i}: {dur:.2f}s of {room:.2f}s {'OK' if dur <= room else 'TOO LONG'}  {line['text']}")
