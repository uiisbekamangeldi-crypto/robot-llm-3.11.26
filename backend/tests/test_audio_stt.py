import io
import wave

import numpy as np
import pytest

from app.modules.audio.stt import LocalSpeechRecognizer, decode_wav


def wav_bytes(samples: np.ndarray, rate: int = 16000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(samples.astype("<i2").tobytes())
    return buffer.getvalue()


def test_invalid_audio_is_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid WAV"):
        decode_wav(b"not audio")


def test_audio_is_resampled_to_16khz() -> None:
    samples = (np.sin(np.arange(8000) * 0.02) * 12000).astype(np.int16)
    assert len(decode_wav(wav_bytes(samples, 8000))) == 16000


@pytest.mark.asyncio
async def test_silence_returns_without_loading_model() -> None:
    recognizer = LocalSpeechRecognizer("small", ".models")
    result = await recognizer.transcribe(wav_bytes(np.zeros(16000, dtype=np.int16)))
    assert result.text == ""
    assert result.language is None
    assert recognizer._model is None
