#!/bin/bash
# Launch script for wyoming-whisperkit LaunchAgent.
# Runs setup on first boot (idempotent), then starts the Wyoming server.
set -e
cd "$(dirname "$0")"
./script/setup
./script/run \
  --uri tcp://0.0.0.0:7892 \
  --model small \
  --bridge ~/containers/home-automation/mac-whisper-speedtest/tools/whisperkit-bridge/.build/release/whisperkit-bridge \
  --debug
