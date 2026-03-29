#!/usr/bin/env python3
"""Wyoming server entry point for wyoming-whisperkit."""
import argparse
import asyncio
import logging
import tempfile
import wave
from functools import partial
from pathlib import Path

import numpy as np
from wyoming.info import AsrModel, AsrProgram, Attribution, Info
from wyoming.server import AsyncServer

from . import __version__
from .handler import WhisperKitEventHandler

_LOGGER = logging.getLogger(__name__)

# ── Wyoming languages list (same as wyoming-mlx-whisper) ─────────────────────
WHISPER_LANGUAGES = [
    "af", "ar", "hy", "az", "be", "bs", "bg", "ca", "zh", "hr",
    "cs", "da", "nl", "en", "et", "fi", "fr", "gl", "de", "el",
    "he", "hi", "hu", "is", "id", "it", "ja", "kn", "kk", "ko",
    "lv", "lt", "mk", "ms", "mr", "mi", "ne", "no", "fa", "pl",
    "pt", "ro", "ru", "sr", "sk", "sl", "es", "sw", "sv", "tl",
    "ta", "th", "tr", "uk", "ur", "vi", "cy",
]


async def main() -> None:
    parser = argparse.ArgumentParser(description="Wyoming server for WhisperKit STT")
    parser.add_argument(
        "--bridge",
        default="~/containers/home-automation/mac-whisper-speedtest/tools/whisperkit-bridge/.build/release/whisperkit-bridge",
        help="Path to compiled whisperkit-bridge binary",
    )
    parser.add_argument(
        "--model",
        default="small",
        help="WhisperKit model name (tiny | base | small | medium | large-v3)",
    )
    parser.add_argument("--uri", required=True, help="tcp://0.0.0.0:PORT or unix://PATH")
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging")
    parser.add_argument(
        "--log-format", default=logging.BASIC_FORMAT, help="Python logging format string"
    )
    parser.add_argument("--version", action="version", version=__version__)

    vad_group = parser.add_mutually_exclusive_group()
    vad_group.add_argument(
        "--vad", action="store_true", default=True,
        help="Enable Silero-VAD early-trigger (default: on)",
    )
    vad_group.add_argument(
        "--no-vad", dest="vad", action="store_false",
        help="Disable Silero-VAD; wait for ESPHome AudioStop only",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format=args.log_format,
    )
    _LOGGER.debug(args)

    # ── Validate bridge binary ────────────────────────────────────────────────
    bridge_path = Path(args.bridge).expanduser()
    if not bridge_path.exists():
        _LOGGER.error(
            "whisperkit-bridge binary not found at %s\n"
            "Build it with:\n"
            "  cd ~/containers/home-automation/mac-whisper-speedtest/tools/whisperkit-bridge\n"
            "  swift build -c release",
            bridge_path,
        )
        raise SystemExit(1)

    _LOGGER.info("Using whisperkit-bridge: %s", bridge_path)

    # ── Warm up WhisperKit (loads CoreML model into Neural Engine cache) ───────
    # Without a warm-up pass the first inference after boot takes ~10-20 s.
    # We write 1 s of silence to a temp WAV and transcribe it via the bridge.
    _LOGGER.info("Warming up WhisperKit model (%s) — first run loads CoreML graphs…", args.model)
    silence = np.zeros(16000, dtype=np.int16)
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        warmup_path = tmp.name
    try:
        with wave.open(warmup_path, "wb") as wf:
            wf.setparams((1, 2, 16000, 0, "NONE", "NONE"))
            wf.writeframes(silence.tobytes())

        proc = await asyncio.create_subprocess_exec(
            str(bridge_path),
            warmup_path,
            "--format", "json",
            "--model",  args.model,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            _LOGGER.warning(
                "Warm-up returned non-zero (%d): %s",
                proc.returncode,
                stderr.decode(errors="replace").strip(),
            )
        else:
            _LOGGER.info("WhisperKit warm ✓")
    finally:
        Path(warmup_path).unlink(missing_ok=True)

    # ── Silero-VAD setup ──────────────────────────────────────────────────────
    if args.vad:
        _LOGGER.info("Loading Silero-VAD (ONNX backend)…")
        try:
            import torch
            from silero_vad import load_silero_vad

            vad_model = load_silero_vad(onnx=True)
            vad_model.reset_states()
            _warmup_chunk = torch.zeros(512)
            vad_model(_warmup_chunk, 16000)
            WhisperKitEventHandler._vad_model = vad_model
            _LOGGER.info("Silero-VAD ready ✓")
        except Exception as exc:
            _LOGGER.warning("Silero-VAD failed to load — falling back to AudioStop: %s", exc)
            args.vad = False
    else:
        _LOGGER.info("Silero-VAD disabled (--no-vad)")

    # ── Wyoming server info ───────────────────────────────────────────────────
    wyoming_info = Info(
        asr=[
            AsrProgram(
                name="whisperkit",
                description="WhisperKit (Apple Silicon native, CoreML + Neural Engine)",
                attribution=Attribution(
                    name="Argmax Inc.",
                    url="https://github.com/argmaxinc/WhisperKit",
                ),
                installed=True,
                version=__version__,
                models=[
                    AsrModel(
                        name=f"whisperkit-{args.model}",
                        description=f"WhisperKit {args.model} model",
                        attribution=Attribution(
                            name="Argmax Inc.",
                            url="https://huggingface.co/argmaxinc/whisperkit-coreml",
                        ),
                        installed=True,
                        languages=WHISPER_LANGUAGES,
                        version="1.0",
                    )
                ],
            )
        ],
    )

    server = AsyncServer.from_uri(args.uri)
    _LOGGER.info("wyoming-whisperkit ready on %s", args.uri)
    await server.run(partial(WhisperKitEventHandler, wyoming_info, args))


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        pass
