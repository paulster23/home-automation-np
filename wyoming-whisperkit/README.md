# wyoming-whisperkit

Wyoming protocol STT server backed by **WhisperKit** — Apple Silicon native, CoreML + Neural Engine.

Benchmarked at **0.85s avg / 0.52s warmed up** on Mac Mini M1 (small model, vs ~3s for wyoming-mlx-whisper's whisper-small-mlx-4bit).

## Architecture

```
HA satellite (ESPHome)
  └─ AudioChunk events (16 kHz PCM)
       └─ Silero-VAD (early end-of-speech trigger, same as wyoming-mlx-whisper)
            └─ temp WAV file
                 └─ whisperkit-bridge (Swift, CoreML, Apple Neural Engine)
                      └─ JSON { "text": "...", "transcription_time": 0.85 }
                           └─ Wyoming Transcript event → HA
```

## Port

**7892** (wyoming-mlx-whisper stays on 7891 — both can run simultaneously for A/B comparison)

## Prerequisites

The `whisperkit-bridge` Swift binary must already be compiled:

```bash
cd ~/containers/home-automation/mac-whisper-speedtest/tools/whisperkit-bridge
swift build -c release
```

The release binary will be at `.build/release/whisperkit-bridge`.

## Install

```bash
cd ~/containers/home-automation/wyoming-whisperkit
chmod +x install_service.sh uninstall_service.sh wyoming-whisperkit.sh script/setup script/run
./install_service.sh
```

Logs:
```bash
tail -f log/whisper.log
tail -f log/whisper.err
```

## Switch HA to use WhisperKit

1. **Settings → Integrations → Wyoming Protocol**
2. Edit the existing `wyoming-mlx-whisper` entry **or** add a new Wyoming integration
3. Change host/port to `192.168.1.70:7892`
4. Go to **Settings → Voice Assistants → Naboo** and set STT to the new Wyoming entry

## A/B Benchmarking with voice-bench

After switching HA to port 7892, update the voice-bench config tag:

```yaml
# voice-bench/config.yaml
tag: whisperkit-small-silero-vad
notes: "WhisperKit small model via Swift bridge + Silero-VAD"
```

Then restart voice-bench and run a set of commands to populate the CSV.

## Roll back

```bash
# Point HA back to port 7891 (wyoming-mlx-whisper)
# OR:
./uninstall_service.sh
```

## Reload after config changes

```bash
launchctl unload ~/Library/LaunchAgents/com.wyoming.whisperkit.plist
launchctl load  ~/Library/LaunchAgents/com.wyoming.whisperkit.plist
```
