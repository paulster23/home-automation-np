#!/usr/bin/env python3
from pathlib import Path
import setuptools
from setuptools import setup

this_dir = Path(__file__).parent
module_name = "wyoming_whisperkit"

setup(
    name=module_name,
    version="1.0.0",
    description="Wyoming Server for WhisperKit (Apple Silicon native STT)",
    url="https://github.com/argmaxinc/WhisperKit",
    license="MIT",
    packages=setuptools.find_packages(),
    install_requires=(this_dir / "requirements.txt").read_text().splitlines(),
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "wyoming-whisperkit = wyoming_whisperkit.__main__:run"
        ]
    },
)
