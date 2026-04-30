"""Event handler for wyoming-whisperkit.

Receives Wyoming AudioChunk events from Home Assistant, runs Silero-VAD for
fast end-of-speech detection, writes a temporary WAV file, and calls the
compiled whisperkit-bridge binary to transcribe it.  Returns a Wyoming
Transcript event.

Architecture (identical to wyoming-mlx-whisper, SwiftKit backend instead of MLX):

    HA satellite → [AudioChunk…] → Silero-VAD early trigger or AudioStop
                → temp WAV file → whisperkit-bridge (Swift, CoreML / ANE)
                → JSON { "text": "...", "transcription_time": 0.85 }
                → Transcript event → HA
"""
import asyncio
import argparse
import json
import logging
import tempfile
import time
import wave
from pathlib import Path
from typing import Optional

import numpy as np
from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioChunkConverter, AudioStop
from wyoming.event import Event
from wyoming.info import Describe, Info
from wyoming.server import AsyncEventHandler

_LOGGER = logging.getLogger(__name__)

# ── Silero-VAD constants (same tuning as wyoming-mlx-whisper) ─────────────────
VAD_CHUNK_SAMPLES = 512   # 32 ms @ 16 kHz — required by Silero
VAD_THRESHOLD     = 0.5
VAD_MIN_SPEECH_MS = 600   # arm after 600 ms of confirmed speech
VAD_SILENCE_MS    = 700   # trigger 700 ms after speech ends (was 900 — tuned 2026-04-29)
VAD_MAX_SPEECH_MS = 10_000


class WhisperKitEventHandler(AsyncEventHandler):
    """Wyoming ASR handler backed by the native WhisperKit Swift binary."""

    # Shared VAD model — loaded once at startup by __main__.py
    _vad_model = None

    def __init__(
        self,
        wyoming_info: Info,
        cli_args: argparse.Namespace,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.cli_args           = cli_args
        self.wyoming_info_event = wyoming_info.event()
        self.audio_converter    = AudioChunkConverter(rate=16000, width=2, channels=1)

        self._reset_state()

        if self._vad_enabled:
            try:
                self.__class__._vad_model.reset_states()
            except Exception as exc:
                _LOGGER.debug("VAD reset_states failed: %s", exc)

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def _vad_enabled(self) -> bool:
        return (
            getattr(self.cli_args, "vad", False)
            and self.__class__._vad_model is not None
        )

    # ── State ─────────────────────────────────────────────────────────────────

    def _reset_state(self):
        self.audio: bytes = b""
        self._vad_buffer: np.ndarray      = np.empty(0, dtype=np.float32)
        self._vad_speech_chunks: int      = 0
        self._vad_silence_chunks: int     = 0
        self._vad_armed: bool             = False
        self._vad_triggered: bool         = False

    # ── Event dispatch ────────────────────────────────────────────────────────

    async def handle_event(self, event: Event) -> bool:
        if AudioChunk.is_type(event.type):
            if not self.audio:
                _LOGGER.debug("Receiving audio")
            chunk = AudioChunk.from_event(event)
            chunk = self.audio_converter.convert(chunk)
            self.audio += chunk.audio
            if self._vad_enabled and not self._vad_triggered:
                await self._run_vad(chunk.audio)
            return True

        if AudioStop.is_type(event.type):
            _LOGGER.debug("AudioStop received (vad_triggered=%s)", self._vad_triggered)
            if self._vad_triggered:
                self._reset_state()
                return False
            await self._transcribe(trigger="audio_stop")
            return False

        if Transcribe.is_type(event.type):
            _LOGGER.debug("Transcribe event")
            return True

        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info_event)
            _LOGGER.debug("Sent info")
            return True

        return True

    # ── Silero-VAD ─────────────────────────────────────────────────────────────

    async def _run_vad(self, raw_audio: bytes):
        samples = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32) / 32768.0
        self._vad_buffer = np.concatenate([self._vad_buffer, samples])

        while len(self._vad_buffer) >= VAD_CHUNK_SAMPLES:
            window = self._vad_buffer[:VAD_CHUNK_SAMPLES]
            self._vad_buffer = self._vad_buffer[VAD_CHUNK_SAMPLES:]

            speech_prob = self._vad_infer(window)
            if speech_prob is None:
                return

            is_speech = speech_prob >= VAD_THRESHOLD

            if is_speech:
                self._vad_speech_chunks += 1
                self._vad_silence_chunks = 0
            else:
                if self._vad_armed:
                    self._vad_silence_chunks += 1

            speech_ms = self._vad_speech_chunks * 32
            if not self._vad_armed and speech_ms >= VAD_MIN_SPEECH_MS:
                self._vad_armed = True
                _LOGGER.debug("VAD armed (%.0f ms speech)", speech_ms)

            if speech_ms > VAD_MAX_SPEECH_MS:
                _LOGGER.debug("VAD disarmed — speech exceeded cap")
                self._reset_state()
                return

            silence_ms = self._vad_silence_chunks * 32
            if self._vad_armed and silence_ms >= VAD_SILENCE_MS:
                audio_s = len(self.audio) / 2 / 16000
                _LOGGER.info(
                    "VAD early trigger — %.1f s audio collected "
                    "(speech=%.0f ms, silence=%.0f ms)",
                    audio_s, speech_ms, silence_ms,
                )
                self._vad_triggered = True
                await self._transcribe(trigger="vad")
                return

    def _vad_infer(self, window: np.ndarray) -> Optional[float]:
        model = self.__class__._vad_model
        try:
            import torch
            tensor = torch.from_numpy(window.copy())
            result = model(tensor, 16000)
            return result.item() if hasattr(result, "item") else float(result)
        except Exception as exc:
            _LOGGER.warning("VAD inference error: %s", exc)
            return None

    # ── Transcription via WhisperKit ──────────────────────────────────────────

    async def _transcribe(self, trigger: str = "unknown"):
        if not self.audio:
            _LOGGER.debug("No audio to transcribe (trigger=%s)", trigger)
            self._reset_state()
            return

        audio_s = len(self.audio) / 2 / 16000
        _LOGGER.debug("Transcribing %.1f s of audio via WhisperKit (trigger=%s)", audio_s, trigger)

        bridge_bin = Path(self.cli_args.bridge).expanduser()
        model      = self.cli_args.model

        # Write PCM → temp WAV (WhisperKit bridge expects a file path, not stdin)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            with wave.open(tmp_path, "wb") as wf:
                wf.setparams((1, 2, 16000, 0, "NONE", "NONE"))
                wf.writeframes(self.audio)

            t0 = time.time()

            # Run whisperkit-bridge as a subprocess (non-blocking via asyncio)
            proc = await asyncio.create_subprocess_exec(
                str(bridge_bin),
                tmp_path,
                "--format", "json",
                "--model",  model,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            t1 = time.time()

            wall_time = t1 - t0

            if proc.returncode != 0:
                err = stderr.decode(errors="replace").strip()
                _LOGGER.error(
                    "whisperkit-bridge exited %d (%.3f s): %s",
                    proc.returncode, wall_time, err,
                )
                text = ""
            else:
                try:
                    result = json.loads(stdout.decode())
                    text   = result.get("text", "").strip()
                    kit_ms = result.get("transcription_time", 0.0) * 1000
                    _LOGGER.debug(
                        "WhisperKit internal time: %.0f ms  wall: %.0f ms",
                        kit_ms, wall_time * 1000,
                    )
                except json.JSONDecodeError as exc:
                    _LOGGER.error("Failed to parse bridge output: %s", exc)
                    text = ""

            _LOGGER.info(text)

        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass

        await self.write_event(Transcript(text=text).event())
        _LOGGER.debug("Completed request")
        self._reset_state()
