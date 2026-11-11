import asyncio
import io
import wave
from pathlib import Path

from piper import PiperVoice

VOICE_NAMES = {
    "kk": "kk_KZ-issai-high",
    "ru": "ru_RU-irina-medium",
    "en": "en_US-lessac-medium",
}


class LocalSpeechSynthesizer:
    def __init__(self, voice_dir: str, timeout_seconds: float = 30) -> None:
        self.voice_dir = Path(voice_dir)
        self.timeout_seconds = timeout_seconds
        self._voices: dict[str, PiperVoice] = {}
        self._lock = asyncio.Lock()

    def available(self, language: str) -> bool:
        name = VOICE_NAMES.get(language)
        return bool(name and (self.voice_dir / f"{name}.onnx").is_file())

    def _synthesize_sync(self, text: str, language: str) -> bytes:
        voice = self._voices.get(language)
        if voice is None:
            model = self.voice_dir / f"{VOICE_NAMES[language]}.onnx"
            if not model.is_file() or not model.with_suffix(".onnx.json").is_file():
                raise FileNotFoundError(f"No local voice for {language}")
            voice = PiperVoice.load(str(model))
            self._voices[language] = voice
        output = io.BytesIO()
        with wave.open(output, "wb") as wav:
            voice.synthesize_wav(text, wav)
        return output.getvalue()

    async def synthesize(self, text: str, language: str) -> bytes:
        if language not in VOICE_NAMES:
            raise ValueError("Unsupported language")
        if not text.strip() or len(text) > 2000:
            raise ValueError("Text must contain 1–2000 characters")
        async with self._lock:
            result = await asyncio.wait_for(
                asyncio.to_thread(self._synthesize_sync, text, language),
                timeout=self.timeout_seconds,
            )
        with wave.open(io.BytesIO(result), "rb") as wav:
            if wav.getnframes() == 0 or wav.getsampwidth() != 2 or wav.getnchannels() != 1:
                raise ValueError("TTS produced invalid WAV audio")
        return result
