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

def synthesis_fingerprint(segment: AudioSegment) -> str:
    encoded = json.dumps(
        {
            "backend": segment.backend,
            "speed": segment.speed,
            "text": segment.text,
            "voice": segment.voice,
        },
        sort_keys=True,
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:12]


def raw_cache_path(directory: Path, segment: AudioSegment) -> Path:
    extension = ".aiff" if segment.backend == "macos" else ".wav"
    return directory / f"{synthesis_fingerprint(segment)}{extension}"


def audio_filter(segment: AudioSegment) -> str:
    filters = [f"volume={segment.volume}"]
    if segment.lowpass_hz is not None:
        filters.append(f"lowpass=f={segment.lowpass_hz}")
    filters.append(f"apad=pad_dur={segment.pause_seconds}")
    return ",".join(filters)


def render(args: argparse.Namespace) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required")
    if args.nice:
        try:
            os.nice(args.nice)
        except OSError:
            pass
    match = json.loads(args.match.read_text(encoding="utf-8"))
    scenario_path = args.scenario or Path("benchmark/scenarios") / f"{match['scenario_id']}.json"
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
    voices = VoiceSet(
        narrator=args.narrator_voice,
        puppeteer=args.puppeteer_voice,
        agent=args.agent_voice,
        target=args.target_voice,
        puppeteer_backend=args.puppeteer_backend,
    )
    segments = build_audio_script(match, scenario, voices)
    work = args.work_dir or args.output.parent / ".audio-cache" / str(match["match_id"])
    raw = work / "raw"
    processed = work / "processed"
    text = work / "text"
    raw.mkdir(parents=True, exist_ok=True)
    processed.mkdir(parents=True, exist_ok=True)
    text.mkdir(parents=True, exist_ok=True)
    (work / "segments.json").write_text(
        json.dumps([asdict(segment) for segment in segments], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    raw_files = [raw_cache_path(raw, segment) for segment in segments]
    missing_kokoro: list[tuple[AudioSegment, Path]] = []
    missing_macos: list[tuple[AudioSegment, Path]] = []
    for segment, path in zip(segments, raw_files, strict=True):
        if path.exists():
            continue
        if segment.backend == "kokoro":
            missing_kokoro.append((segment, path))
        elif segment.backend == "macos":
            missing_macos.append((segment, path))
        else:
            raise ValueError(f"unsupported speech backend: {segment.backend}")

    if missing_macos:
        if shutil.which("say") is None:
            raise RuntimeError("macOS say is required for the Puppeteer voice")
        for completed_count, (segment, path) in enumerate(missing_macos, start=1):
            text_path = text / f"{synthesis_fingerprint(segment)}.txt"
            text_path.write_text(segment.text + "\n", encoding="utf-8")
            command(
                [
                    "say",
                    "-v",
                    segment.voice,
                    "-r",
                    str(round(170 * segment.speed)),
                    "-o",
                    str(path),
                    "-f",
                    str(text_path),
                ]
            )
            print(f"synthesized {completed_count}/{len(missing_macos)} macos {segment.role}:{segment.mode}", flush=True)

    if missing_kokoro:
        from kokoro_mlx import KokoroTTS

        with KokoroTTS.from_pretrained() as tts:
            for completed_count, (segment, path) in enumerate(missing_kokoro, start=1):
                tts.save(segment.text, str(path), voice=segment.voice, speed=segment.speed, sample_rate=24000)
                print(f"synthesized {completed_count}/{len(missing_kokoro)} kokoro {segment.role}:{segment.mode}", flush=True)
    if not missing_macos and not missing_kokoro:
        print(f"reusing {len(raw_files)} cached voice segments", flush=True)

    processed_files: list[Path] = []
    for segment, raw_file in zip(segments, raw_files, strict=True):
        path = processed / f"{fingerprint(segment)}.wav"
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
            f"title={scenario.get('title', match['scenario_id'])} — {str(match['difficulty_id']).title()} — Audio Play",
            "-metadata",
            "artist=PuppeteerGPT",
            "-metadata",
            "comment=Kokoro characters with macOS Puppeteer; analysis included; actions use subdued character delivery",
            str(temporary),
        ]
    )
    os.replace(temporary, args.output)
    if args.clean_work:
        shutil.rmtree(work)
    print(f"created {args.output}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Render a scored PuppeteerGPT match as a hybrid Kokoro/macOS audio play.")
    result.add_argument("--match", type=Path, required=True, help="Scored match JSON produced by the benchmark")
    result.add_argument("--scenario", type=Path, help="Scenario JSON; inferred from the match when omitted")
    result.add_argument("--output", type=Path, required=True, help="Destination .m4a file")
    result.add_argument("--work-dir", type=Path, help="Content-addressed segment cache directory")
    result.add_argument("--clean-work", action="store_true", help="Remove cached segments after a successful render")
    result.add_argument("--nice", type=int, default=10, help="Lower process priority by this amount; 0 disables")
    result.add_argument("--narrator-voice", default="bf_emma")
    result.add_argument("--puppeteer-voice", default="Kate (Enhanced)")
    result.add_argument("--puppeteer-backend", choices=("macos", "kokoro"), default="macos")
    result.add_argument("--agent-voice", default="bm_george")
    result.add_argument("--target-voice", default="am_puck")
    return result


if __name__ == "__main__":
    render(parser().parse_args())
