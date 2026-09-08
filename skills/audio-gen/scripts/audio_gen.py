#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audio-gen: OpenAI-compatible text-to-speech CLI.

Subcommand:
  generate --text "..." -> POST /v1/audio/speech (text to audio)

Defaults: model=gpt-4o-mini-tt, voice=alloy, response_format=mp3, speed=1.0,
out=output/audio-gen/output.mp3 (auto-versioned when the file already exists).

The API key is read only from the AUDIOGEN_API_KEY environment variable
(no hardcoded key in the source). The key is never printed to stdout/stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

# ---------------------------------------------------------------------------
# Endpoint / credentials
# ---------------------------------------------------------------------------
ENV_API_KEY = "AUDIOGEN_API_KEY"
ENV_BASE_URL = "AUDIOGEN_API_BASE_URL"
DEFAULT_API_BASE_URL = "https://www.aivalux.com/v1"

# The default base URL is the same aivalux gateway used by imagegen2, but that
# gateway currently only serves images (no /v1/audio/* route). Point
# AUDIOGEN_API_BASE_URL at a TTS-capable OpenAI-compatible endpoint when needed.
API_BASE_URL = os.getenv(ENV_BASE_URL, DEFAULT_API_BASE_URL).rstrip("/")
ENDPOINT_SPEECH = f"{API_BASE_URL}/audio/speech"

# ---------------------------------------------------------------------------
# Defaults and allowed values
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "gpt-4o-mini-tt"
DEFAULT_VOICE = "alloy"
DEFAULT_FORMAT = "mp3"
DEFAULT_OUT_PATH = "output/audio-gen/output.mp3"
DEFAULT_TIMEOUT = 120

ALLOWED_MODELS = {"gpt-4o-mini-tt"}
ALLOWED_VOICES = {
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "onyx",
    "nova",
    "sage",
    "shimmer",
    "verse",
}
ALLOWED_FORMATS = {"mp3", "opus", "aac", "flac", "wav", "pcm"}
FORMAT_EXT = {
    "mp3": ".mp3",
    "opus": ".opus",
    "aac": ".aac",
    "flac": ".flac",
    "wav": ".wav",
    "pcm": ".pcm",
}
MIN_SPEED, MAX_SPEED = 0.25, 4.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _die(message: str, code: int = 1) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(code)


def _warn(message: str) -> None:
    print(f"Warning: {message}", file=sys.stderr)


def _log(message: str) -> None:
    print(message, file=sys.stderr)


def _api_key() -> str:
    """Read the API key from the AUDIOGEN_API_KEY env var (never hardcoded)."""
    key = os.getenv(ENV_API_KEY, "").strip()
    if not key:
        _die(
            f"environment variable {ENV_API_KEY} is not set; "
            "set it first, e.g. export AUDIOGEN_API_KEY=sk-..."
        )
    return key


def _normalize_format(fmt: Optional[str]) -> str:
    if not fmt:
        return DEFAULT_FORMAT
    fmt = fmt.lower()
    if fmt not in ALLOWED_FORMATS:
        _die("--format must be one of mp3, opus, aac, flac, wav, pcm.")
    return fmt


def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    index = 2
    while True:
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _resolve_out_path(out: str, output_format: str, force: bool) -> Path:
    ext = FORMAT_EXT[output_format]
    out_path = Path(out)
    if out_path.suffix == "" or out_path.suffix.lstrip(".").lower() != output_format:
        out_path = out_path.with_suffix(ext)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return out_path if force else _unique_path(out_path)


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------
def _decode_error(response: requests.Response) -> str:
    try:
        data = response.json()
    except json.JSONDecodeError:
        return (response.text or "")[:300]
    if isinstance(data, dict):
        err = data.get("error", data)
        if isinstance(err, dict):
            return err.get("message") or err.get("code") or json.dumps(err)
        return str(err)
    return json.dumps(data, ensure_ascii=False)[:300]


def _post_speech(payload: Dict[str, Any], timeout: int) -> bytes:
    attempt = 1
    max_attempts = 3
    while True:
        try:
            headers = {
                "Authorization": f"Bearer {_api_key()}",
                "Content-Type": "application/json",
            }
            response = requests.post(
                ENDPOINT_SPEECH, headers=headers, json=payload, timeout=(30, timeout)
            )
        except requests.exceptions.Timeout:
            _warn(f"request timed out (attempt {attempt}/{max_attempts}).")
            attempt += 1
            if attempt > max_attempts:
                _die("request failed after repeated timeouts.")
            time.sleep(2 * attempt)
            continue
        except requests.exceptions.RequestException as exc:
            _die(f"network error: {exc}")

        if response.status_code in {429, 500, 502, 503, 504} and attempt < max_attempts:
            _warn(f"server returned {response.status_code}; retrying (attempt {attempt}).")
            attempt += 1
            time.sleep(2 * attempt)
            continue

        if response.status_code >= 400:
            _die(f"API error (HTTP {response.status_code}): {_decode_error(response)}")

        content = response.content
        if not content:
            _die("API returned an empty audio response.")
        return content


# ---------------------------------------------------------------------------
# Payload building
# ---------------------------------------------------------------------------
def _build_payload(args: argparse.Namespace) -> Dict[str, Any]:
    text = (args.text or "").strip()
    if not text:
        _die('missing text. Use --text "..."')

    output_format = _normalize_format(args.format)
    payload: Dict[str, Any] = {
        "model": args.model,
        "input": text,
        "voice": args.voice,
        "response_format": output_format,
        "speed": args.speed,
    }
    if args.instructions:
        payload["instructions"] = args.instructions.strip()

    args._out_path = _resolve_out_path(args.out, output_format, args.force)
    return payload


def _print_dry_run(args: argparse.Namespace, payload: Dict[str, Any]) -> None:
    preview = {k: v for k, v in payload.items() if v is not None}
    request = {
        "endpoint": ENDPOINT_SPEECH,
        "output": str(args._out_path),
        **preview,
    }
    _log("Dry-run request (no API key shown):")
    _log(json.dumps(request, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Subcommand
# ---------------------------------------------------------------------------
def _handle_generate(args: argparse.Namespace) -> None:
    payload = _build_payload(args)
    if args.dry_run:
        _print_dry_run(args, payload)
        return
    _log(f"Calling {ENDPOINT_SPEECH} (text-to-speech)...")
    started = time.time()
    audio = _post_speech(payload, timeout=args.timeout)
    _log(f"Synthesis finished in {time.time() - started:.1f}s.")
    args._out_path.write_bytes(audio)
    _log(f"Saved {args._out_path.resolve()}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="audio-gen: OpenAI-compatible text-to-speech CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    gen_parser = subparsers.add_parser(
        "generate", help="text-to-speech via /v1/audio/speech"
    )
    gen_parser.add_argument("--text", help="text to synthesize (required)")
    gen_parser.add_argument(
        "--model", default=DEFAULT_MODEL, choices=sorted(ALLOWED_MODELS)
    )
    gen_parser.add_argument(
        "--voice", default=DEFAULT_VOICE, choices=sorted(ALLOWED_VOICES)
    )
    gen_parser.add_argument(
        "--format", "--response-format", dest="format",
        default=DEFAULT_FORMAT, choices=sorted(ALLOWED_FORMATS),
    )
    gen_parser.add_argument("--speed", type=float, default=1.0, help="speech speed 0.25-4.0")
    gen_parser.add_argument("--instructions", help="optional extra voice/style instructions")
    gen_parser.add_argument("--out", default=DEFAULT_OUT_PATH, help="output file path")
    gen_parser.add_argument("--force", action="store_true", help="overwrite existing files")
    gen_parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="API timeout seconds")
    gen_parser.add_argument(
        "--dry-run", action="store_true", help="print the request without sending it"
    )
    gen_parser.set_defaults(func=_handle_generate)

    args = parser.parse_args()
    if not (MIN_SPEED <= args.speed <= MAX_SPEED):
        _die(f"--speed must be between {MIN_SPEED} and {MAX_SPEED}.")

    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
