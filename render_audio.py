# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["kokoro-mlx>=0.1,<1"]
# ///

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

from puppeteergpt.audio import AudioSegment, VoiceSet, build_audio_script


def command(arguments: list[str]) -> None:
    completed = subprocess.run(arguments, capture_output=True, text=True)
    if completed.returncode:
        raise RuntimeError(f"command failed: {' '.join(arguments)}\n{completed.stderr}")


def fingerprint(segment: AudioSegment) -> str:
    encoded = json.dumps(asdict(segment), sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:12]


def audio_filter(segment: AudioSegment) -> str:
    filters = [f"volume={segment.volume}"]
    if segment.lowpass_hz is not None:
        filters.append(f"lowpass=f={segment.lowpass_hz}")
    filters.append(f"apad=pad_dur={segment.pause_seconds}")
    return ",".join(filters)


def render(args: argparse.Namespace) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required")
    match = json.loads(args.match.read_text(encoding="utf-8"))
    scenario_path = args.scenario or Path("benchmark/scenarios") / f"{match['scenario_id']}.json"
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    voices = VoiceSet(args.narrator_voice, args.puppeteer_voice, args.agent_voice, args.target_voice)
    segments = build_audio_script(match, scenario, voices)
    work = args.work_dir or args.output.parent / ".kokoro-cache" / str(match["match_id"])
    raw = work / "raw"
    processed = work / "processed"
    raw.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    (work / "segments.json").write_text(
        json.dumps([asdict(segment) for segment in segments], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    raw_files: list[Path] = []
    missing: list[tuple[int, AudioSegment, Path]] = []
    for index, segment in enumerate(segments):
        path = raw / f"{index:03d}-{fingerprint(segment)}.wav"
        raw_files.append(path)
        if not path.exists():
            missing.append((index, segment, path))
    if missing:
        from kokoro_mlx import KokoroTTS

        with KokoroTTS.from_pretrained() as tts:
            for completed_count, (index, segment, path) in enumerate(missing, start=1):
                tts.save(segment.text, str(path), voice=segment.voice, speed=segment.speed, sample_rate=24000)
                print(f"synthesized {completed_count}/{len(missing)} {segment.role}:{segment.mode}", flush=True)
    else:
        print(f"reusing {len(raw_files)} cached voice segments", flush=True)

    processed_files: list[Path] = []
    for index, (segment, raw_file) in enumerate(zip(segments, raw_files, strict=True)):
        path = processed / f"{index:03d}-{fingerprint(segment)}.wav"
        processed_files.append(path)
        if path.exists():
            continue
        command(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(raw_file),
                "-af",
                audio_filter(segment),
                "-ar",
                "24000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(path),
            ]
        )

    concat = work / "concat.txt"
    concat.write_text("\n".join(f"file '{path.resolve()}'" for path in processed_files) + "\n", encoding="utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(f".{args.output.stem}.tmp{args.output.suffix}")
    command(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat),
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "48000",
            "-ac",
            "1",
            "-metadata",
            f"title={scenario.get('title', match['scenario_id'])} — {str(match['difficulty_id']).title()} — Kokoro",
            "-metadata",
            "artist=PuppeteerGPT",
            "-metadata",
            "comment=Kokoro MLX; Puppeteer analysis included; actions use subdued character delivery",
            str(temporary),
        ]
    )
    os.replace(temporary, args.output)
    if args.clean_work:
        shutil.rmtree(work)
    print(f"created {args.output}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Render a scored PuppeteerGPT match as a Kokoro audio play.")
    result.add_argument("--match", type=Path, required=True, help="Scored match JSON produced by the benchmark")
    result.add_argument("--scenario", type=Path, help="Scenario JSON; inferred from the match when omitted")
    result.add_argument("--output", type=Path, required=True, help="Destination .m4a file")
    result.add_argument("--work-dir", type=Path, help="Segment cache directory")
    result.add_argument("--clean-work", action="store_true", help="Remove cached segments after a successful render")
    result.add_argument("--narrator-voice", default="bf_emma")
    result.add_argument("--puppeteer-voice", default="bf_isabella")
    result.add_argument("--agent-voice", default="bm_fable")
    result.add_argument("--target-voice", default="am_puck")
    return result


if __name__ == "__main__":
    render(parser().parse_args())
