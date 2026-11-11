"""Explicitly download the local models required by the backend."""

import argparse
import shutil
from pathlib import Path

from huggingface_hub import hf_hub_download, snapshot_download

QWEN_REPO = "Qwen/Qwen2.5-1.5B-Instruct-GGUF"
QWEN_FILE = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
VOICES = (
    ("en/en_US/lessac/medium", "en_US-lessac-medium"),
    ("ru/ru_RU/irina/medium", "ru_RU-irina-medium"),
    ("kk/kk_KZ/issai/high", "kk_KZ-issai-high"),
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("component", choices=("all", "llm", "stt", "voices"))
    parser.add_argument("--output", type=Path, default=Path(".models"))
    args = parser.parse_args()
    root: Path = args.output
    if args.component in ("all", "llm"):
        output = root / "llm"
        output.mkdir(parents=True, exist_ok=True)
        downloaded = hf_hub_download(QWEN_REPO, QWEN_FILE)
        shutil.copy2(downloaded, output / QWEN_FILE)
        print("LLM ready")
    if args.component in ("all", "stt"):
        output = root / "whisper" / "small"
        snapshot_download(
            repo_id="Systran/faster-whisper-small",
            local_dir=output,
            allow_patterns=["model.bin", "config.json", "tokenizer.json", "vocabulary.txt"],
        )
        print("STT ready")
    if args.component in ("all", "voices"):
        output = root / "voices"
        output.mkdir(parents=True, exist_ok=True)
        for folder, name in VOICES:
            for suffix in ("", ".json"):
                filename = f"{folder}/{name}.onnx{suffix}"
                downloaded = hf_hub_download("rhasspy/piper-voices", filename)
                shutil.copy2(downloaded, output / f"{name}.onnx{suffix}")
        print("Piper voices ready")


if __name__ == "__main__":
    main()
