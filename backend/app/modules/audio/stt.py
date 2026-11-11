import asyncio
import io
import wave
from dataclasses import dataclass

import numpy as np
from faster_whisper import WhisperModel  # type: ignore[import-untyped]


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str | None
    probability: float


def decode_wav(data: bytes, max_seconds: int = 30) -> np.ndarray:
    if len(data) > 10_000_000:
        raise ValueError("Audio file is too large")
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            channels = wav.getnchannels()
            rate = wav.getframerate()
            width = wav.getsampwidth()
            frames = wav.getnframes()
            if channels not in (1, 2) or width != 2 or not 8000 <= rate <= 48000:
                raise ValueError("Expected mono/stereo 16-bit PCM WAV at 8–48 kHz")
            if frames == 0 or frames / rate > max_seconds:
                raise ValueError("Audio is empty or exceeds duration limit")
            raw = wav.readframes(frames)
    except (EOFError, wave.Error) as exc:
        raise ValueError("Invalid WAV file") from exc
    samples = np.frombuffer(raw, dtype="<i2").reshape(-1, channels).astype(np.float32)
    mono = samples.mean(axis=1) / 32768.0
    if float(np.max(np.abs(mono))) < 0.002:
        return np.array([], dtype=np.float32)
    if rate == 16000:
        return mono
    positions = np.arange(round(len(mono) * 16000 / rate), dtype=np.float64) * rate / 16000
    return np.asarray(np.interp(positions, np.arange(len(mono)), mono), dtype=np.float32)


class LocalSpeechRecognizer:
    def __init__(self, model_name: str, cache_dir: str, timeout_seconds: float = 45) -> None:
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.timeout_seconds = timeout_seconds
        self._model: WhisperModel | None = None
        self._lock = asyncio.Lock()

    def _transcribe_sync(self, audio: np.ndarray, language: str | None) -> Transcript:
        if self._model is None:
            self._model = WhisperModel(
                self.model_name, device="cpu", compute_type="int8", download_root=self.cache_dir
            )
        segments, info = self._model.transcribe(
            audio,
            language=language,
            beam_size=3,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        return Transcript(text, info.language if text else None, info.language_probability)

    async def transcribe(self, data: bytes, language: str | None = None) -> Transcript:
        if language is not None and language not in {"kk", "ru", "en"}:
            raise ValueError("Unsupported language")
        audio = await asyncio.to_thread(decode_wav, data)
        if not len(audio):
            return Transcript("", None, 0.0)
        async with self._lock:
            return await asyncio.wait_for(
                asyncio.to_thread(self._transcribe_sync, audio, language),
                timeout=self.timeout_seconds,
            )
