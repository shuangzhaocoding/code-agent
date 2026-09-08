#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""imagegen2: OpenAI-compatible image generation & editing CLI.

Two subcommands:
  generate  --prompt "..."           -> POST /v1/images/generations (text to image)
  edit      --image A [--image B...] -> POST /v1/images/edits (multipart, reference/edit images)
                       --prompt "..."

Defaults: model=gpt-image-2, quality=medium, output_format=png, n=1,
out=output/imagegen2/output.png (auto-versioned when the file already exists).

The API key is read only from the IMAGEGEN2_API_KEY environment variable
(no hardcoded key in the source). The key is never printed to stdout/stderr.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# ---------------------------------------------------------------------------
# Endpoint / credentials
# ---------------------------------------------------------------------------
API_BASE_URL = "https://www.aivalux.com/v1"
ENDPOINT_GENERATE = f"{API_BASE_URL}/images/generations"
ENDPOINT_EDIT = f"{API_BASE_URL}/images/edits"

ENV_API_KEY = "IMAGEGEN2_API_KEY"

# ---------------------------------------------------------------------------
# Defaults and allowed values
# ---------------------------------------------------------------------------
DEFAULT_MODEL = "gpt-image-2"
DEFAULT_QUALITY = "medium"
DEFAULT_OUTPUT_FORMAT = "png"
DEFAULT_OUT_PATH = "output/imagegen2/output.png"
DEFAULT_TIMEOUT = 600

ALLOWED_MODELS = {"gpt-image-2", "gpt-image-1.5", "gpt-image-1"}
ALLOWED_RATIOS = {"1:1", "16:9", "4:3", "3:4", "9:16"}
ALLOWED_CLARITIES = {"1K", "2K", "4K"}
ALLOWED_QUALITIES = {"low", "medium", "high", "auto"}
ALLOWED_BACKGROUNDS = {"auto", "transparent"}
ALLOWED_FORMATS = {"png", "webp", "jpeg"}
TRANSPARENT_FORMATS = {"png", "webp"}
LEGACY_SIZES = {"1024x1024", "1536x1024", "1024x1536", "auto"}
MAX_IMAGE_BYTES = 50 * 1024 * 1024

# gpt-image-2 size constraints (OpenAI-compatible)
GPT_IMAGE_2_MAX_EDGE = 3840
GPT_IMAGE_2_MIN_PIXELS = 655_360
GPT_IMAGE_2_MAX_PIXELS = 8_294_400
GPT_IMAGE_2_MAX_RATIO = 3.0

# ratio -> {clarity: "WIDTHxHEIGHT"}; every entry satisfies gpt-image-2 constraints.
SIZE_MATRIX: Dict[str, Dict[str, str]] = {
    "1:1": {"1K": "1024x1024", "2K": "2048x2048", "4K": "2880x2880"},
    "16:9": {"1K": "1536x864", "2K": "2048x1152", "4K": "3840x2160"},
    "9:16": {"1K": "864x1536", "2K": "1152x2048", "4K": "2160x3840"},
    "4:3": {"1K": "1024x768", "2K": "2048x1536", "4K": "2880x2160"},
    "3:4": {"1K": "768x1024", "2K": "1536x2048", "4K": "2160x2880"},
}
# clarity given without a ratio -> square by default; 4K follows the common 16:9 UHD size.
CLARITY_ONLY_FALLBACK = {"1K": "1024x1024", "2K": "2048x2048", "4K": "3840x2160"}


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
    """Read the API key from the IMAGEGEN2_API_KEY env var (never hardcoded)."""
    key = os.getenv(ENV_API_KEY, "").strip()
    if not key:
        _die(
            f"environment variable {ENV_API_KEY} is not set; "
            "set it first, e.g. export IMAGEGEN2_API_KEY=sk-..."
        )
    return key


def _normalize_format(fmt: Optional[str]) -> str:
    if not fmt:
        return DEFAULT_OUTPUT_FORMAT
    fmt = fmt.lower()
    if fmt == "jpg":
        return "jpeg"
    if fmt not in ALLOWED_FORMATS:
        _die("--format must be one of png, webp, jpeg (jpg is accepted as jpeg).")
    return fmt


def _parse_size(size: str) -> Tuple[int, int]:
    match = re.fullmatch(r"([1-9][0-9]*)x([1-9][0-9]*)", size)
    if not match:
        _die(f"size must be WIDTHxHEIGHT (e.g. 1024x1024) or auto; got: {size}")
    return int(match.group(1)), int(match.group(2))


def _validate_gpt_image_2_size(size: str) -> None:
    if size == "auto":
        return
    width, height = _parse_size(size)
    max_edge, min_edge = max(width, height), min(width, height)
    if max_edge > GPT_IMAGE_2_MAX_EDGE:
        _die("gpt-image-2 size max edge must be <= 3840px.")
    if width % 16 != 0 or height % 16 != 0:
        _die("gpt-image-2 size width and height must be multiples of 16px.")
    if max_edge / min_edge > GPT_IMAGE_2_MAX_RATIO:
        _die("gpt-image-2 long/short edge ratio must be <= 3:1.")
    total = width * height
    if not (GPT_IMAGE_2_MIN_PIXELS <= total <= GPT_IMAGE_2_MAX_PIXELS):
        _die("gpt-image-2 size total pixels must be within 655,360 and 8,294,400.")


def _resolve_size(ratio: Optional[str], clarity: Optional[str]) -> Optional[str]:
    """Map ratio/clarity to an API size. None means 'unspecified' -> send no size."""
    if ratio and clarity:
        return SIZE_MATRIX[ratio][clarity]
    if ratio:  # ratio only -> 1K tier of that ratio
        return SIZE_MATRIX[ratio]["1K"]
    if clarity:  # clarity only -> square default (4K -> 16:9 UHD)
        return CLARITY_ONLY_FALLBACK[clarity]
    return None


def _adjust_size_for_legacy(model: str, size: Optional[str]) -> Optional[str]:
    """gpt-image-1.5 / gpt-image-1 accept only a small legacy size set."""
    if model == DEFAULT_MODEL or size is None or size in LEGACY_SIZES:
        return size
    width, height = _parse_size(size)
    if width > height:
        adjusted = "1536x1024"
    elif height > width:
        adjusted = "1024x1536"
    else:
        adjusted = "1024x1024"
    _warn(f"model {model} does not support size {size}; using {adjusted} instead.")
    return adjusted


def _resolve_background_model(
    model: str, background: Optional[str], output_format: str, auto_switch: bool
) -> str:
    """Transparent background is unsupported on gpt-image-2: auto-switch to 1.5."""
    if background != "transparent":
        return model
    if output_format not in TRANSPARENT_FORMATS:
        _die("transparent background requires --format png or webp.")
    if model == DEFAULT_MODEL:
        if not auto_switch:
            _die(
                "gpt-image-2 does not support a transparent background. Confirm one of: "
                "1) --model gpt-image-1.5 --background transparent, or 2) --background auto."
            )
        _warn("gpt-image-2 does not support transparent; auto-switched model to gpt-image-1.5.")
        return "gpt-image-1.5"
    return model


# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------
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


def _build_output_paths(
    out: str, out_dir: Optional[str], output_format: str, count: int, force: bool
) -> List[Path]:
    ext = "." + output_format
    if out_dir:
        base = Path(out_dir)
        base.mkdir(parents=True, exist_ok=True)
        paths: List[Path] = []
        for i in range(1, count + 1):
            candidate = base / f"image_{i}{ext}"
            paths.append(candidate if force else _unique_path(candidate))
        return paths

    out_path = Path(out)
    if out_path.suffix == "" or out_path.suffix.lstrip(".").lower() != output_format:
        out_path = out_path.with_suffix(ext)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if count == 1:
        return [out_path if force else _unique_path(out_path)]
    result: List[Path] = []
    for i in range(1, count + 1):
        candidate = out_path.with_name(f"{out_path.stem}-{i}{out_path.suffix}")
        result.append(candidate if force else _unique_path(candidate))
    return result


# ---------------------------------------------------------------------------
# HTTP layer
# ---------------------------------------------------------------------------
class _ImageBundle:
    """Context manager that opens --image files as multipart uploads."""

    def __init__(self, paths: List[Path]):
        self._paths = paths
        self._handles = []

    def __enter__(self) -> List[Tuple[str, Tuple[str, Any, str]]]:
        self._handles = []
        for p in self._paths:
            mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            self._handles.append(("image", (p.name, open(p, "rb"), mime)))
        return self._handles

    def __exit__(self, exc_type, exc, tb):
        for _, entry in self._handles:
            try:
                entry[1].close()
            except Exception:
                pass
        return False


def _check_images(raw_paths: List[str]) -> List[Path]:
    paths = [Path(p) for p in raw_paths]
    for p in paths:
        if not p.exists():
            _die(f"image file not found: {p}")
        if p.stat().st_size > MAX_IMAGE_BYTES:
            _warn(f"image exceeds 50MB limit: {p}")
    return paths


def _post_with_retry(
    url: str,
    body: Dict[str, Any],
    timeout: int,
    files: Optional[List[Tuple[str, Tuple[str, Any, str]]]] = None,
    max_attempts: int = 3,
) -> List[Dict[str, Any]]:
    attempt = 1
    retried_without_background = False
    while True:
        try:
            headers = {"Authorization": f"Bearer {_api_key()}"}
            if files:
                response = requests.post(
                    url, headers=headers, data=body, files=files, timeout=(30, timeout)
                )
            else:
                headers["Content-Type"] = "application/json"
                response = requests.post(url, headers=headers, json=body, timeout=(30, timeout))
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

        # Some OpenAI-compatible proxies reject the `background` field outright.
        # background=auto equals the API default, so retry once without the field.
        if (
            response.status_code == 400
            and body.get("background") == "auto"
            and not retried_without_background
            and "background" in (response.text or "").lower()
        ):
            _warn("API rejected the background parameter; retrying without it.")
            retried_without_background = True
            body = {k: v for k, v in body.items() if k != "background"}
            continue

        return _decode_response(response)


def _decode_response(response: requests.Response) -> List[Dict[str, Any]]:
    try:
        data = response.json()
    except json.JSONDecodeError:
        _die(f"API returned non-JSON (HTTP {response.status_code}): {(response.text or '')[:300]}")
    if response.status_code >= 400:
        err = data.get("error", data) if isinstance(data, dict) else data
        message = (
            err.get("message") or err.get("code") or json.dumps(err)
            if isinstance(err, dict)
            else str(err)
        )
        _die(f"API error (HTTP {response.status_code}): {message}")
    items = data.get("data", []) if isinstance(data, dict) else []
    if not items:
        _die(f"API response contained no image data: {json.dumps(data, ensure_ascii=False)[:300]}")
    return items


def _save_item(item: Dict[str, Any], path: Path) -> None:
    b64 = item.get("b64_json")
    url = item.get("url")
    raw: Optional[bytes] = None
    if b64:
        raw = base64.b64decode(b64)
    elif url:
        _log(f"Downloading image from: {url}")
        fetched = requests.get(url, timeout=(30, 300))
        fetched.raise_for_status()
        raw = fetched.content
    else:
        _die("image item has neither b64_json nor url.")
    path.write_bytes(raw)
    _log(f"Saved {path.resolve()}")


# ---------------------------------------------------------------------------
# Payload building
# ---------------------------------------------------------------------------
def _build_payload(args: argparse.Namespace, *, for_edit: bool) -> Dict[str, Any]:
    prompt = (args.prompt or "").strip()
    if not prompt:
        _die('missing prompt. Use --prompt "..."')

    output_format = _normalize_format(args.format)
    model = _resolve_background_model(
        args.model, args.background, output_format, auto_switch=not args.no_auto_switch
    )

    size: Optional[str] = args.size
    if not size:
        size = _resolve_size(args.ratio, args.clarity)
    if model == DEFAULT_MODEL:
        if size is not None:
            _validate_gpt_image_2_size(size)
    else:
        size = _adjust_size_for_legacy(model, size)

    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "n": args.n,
        "quality": args.quality,
        "background": args.background,
        "output_format": output_format,
    }
    if size is not None:
        payload["size"] = size

    args._output_paths = _build_output_paths(
        args.out, args.out_dir, output_format, args.n, args.force
    )
    return payload


def _print_dry_run(args: argparse.Namespace, payload: Dict[str, Any]) -> None:
    preview = {k: v for k, v in payload.items() if v is not None}
    endpoint = ENDPOINT_GENERATE if args.command == "generate" else ENDPOINT_EDIT
    request = {
        "endpoint": endpoint,
        "outputs": [str(p) for p in args._output_paths],
        **preview,
    }
    _log("Dry-run request (no API key shown):")
    _log(json.dumps(request, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------
def _handle_generate(args: argparse.Namespace) -> None:
    payload = _build_payload(args, for_edit=False)
    if args.dry_run:
        _print_dry_run(args, payload)
        return
    _log(f"Calling {ENDPOINT_GENERATE} (generation)...")
    started = time.time()
    items = _post_with_retry(ENDPOINT_GENERATE, payload, timeout=args.timeout)
    _log(f"Generation finished in {time.time() - started:.1f}s.")
    for item, path in zip(items, args._output_paths):
        _save_item(item, path)


def _handle_edit(args: argparse.Namespace) -> None:
    image_paths = _check_images(args.image)
    payload = _build_payload(args, for_edit=True)
    if args.dry_run:
        _print_dry_run(args, payload)
        return
    _log(f"Calling {ENDPOINT_EDIT} (edit) with {len(image_paths)} image(s)...")
    started = time.time()
    with _ImageBundle(image_paths) as files:
        items = _post_with_retry(ENDPOINT_EDIT, payload, files=files, timeout=args.timeout)
    _log(f"Edit finished in {time.time() - started:.1f}s.")
    for item, path in zip(items, args._output_paths):
        _save_item(item, path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _add_shared_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--prompt", help="image description (required)")
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=sorted(ALLOWED_MODELS))
    parser.add_argument("--n", type=int, default=1, help="number of images (1-10)")
    parser.add_argument(
        "--ratio", choices=sorted(ALLOWED_RATIOS),
        help="aspect ratio: 1:1 / 16:9 / 4:3 / 3:4 / 9:16",
    )
    parser.add_argument(
        "--clarity", choices=sorted(ALLOWED_CLARITIES), help="resolution tier: 1K / 2K / 4K"
    )
    parser.add_argument(
        "--size", help="explicit size e.g. 1024x1024 or auto (overrides ratio/clarity)"
    )
    parser.add_argument("--quality", default=DEFAULT_QUALITY, choices=sorted(ALLOWED_QUALITIES))
    parser.add_argument(
        "--background", default="auto", choices=sorted(ALLOWED_BACKGROUNDS),
        help="auto background (default) or transparent",
    )
    parser.add_argument(
        "--format", "--output-format", dest="format",
        default=DEFAULT_OUTPUT_FORMAT, choices=sorted(ALLOWED_FORMATS),
    )
    parser.add_argument("--out", default=DEFAULT_OUT_PATH, help="output file path")
    parser.add_argument(
        "--out-dir", help="output directory (writes image_1.ext, image_2.ext, ...)"
    )
    parser.add_argument("--force", action="store_true", help="overwrite existing files")
    parser.add_argument(
        "--no-auto-switch", action="store_true",
        help="disable automatic model switch for transparent background (ask instead)",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="API timeout seconds")
    parser.add_argument(
        "--dry-run", action="store_true", help="print the request without sending it"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="imagegen2: OpenAI-compatible image generation/edit CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    gen_parser = subparsers.add_parser(
        "generate", help="text-to-image via /v1/images/generations"
    )
    _add_shared_args(gen_parser)
    gen_parser.set_defaults(func=_handle_generate)

    edit_parser = subparsers.add_parser(
        "edit", help="reference/edit images via /v1/images/edits"
    )
    _add_shared_args(edit_parser)
    edit_parser.add_argument(
        "--image", action="append", default=[],
        help="input/reference image path (repeatable; required)",
    )
    edit_parser.set_defaults(func=_handle_edit)

    args = parser.parse_args()
    if not (1 <= args.n <= 10):
        _die("--n must be between 1 and 10.")
    if args.command == "edit" and not args.image:
        _die("edit requires at least one --image.")
    if args.command == "generate" and getattr(args, "image", None):
        _warn("generate ignores --image; use the edit subcommand for reference/edit images.")

    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
