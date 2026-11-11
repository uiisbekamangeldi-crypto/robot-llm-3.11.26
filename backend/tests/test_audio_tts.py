from pathlib import Path

import pytest

from app.modules.audio.tts import LocalSpeechSynthesizer


@pytest.mark.asyncio
async def test_missing_voice_fails_closed(tmp_path: Path) -> None:
    synth = LocalSpeechSynthesizer(str(tmp_path))
    assert not synth.available("kk")
    with pytest.raises(FileNotFoundError, match="No local voice"):
        await synth.synthesize("Сәлем", "kk")


@pytest.mark.asyncio
async def test_invalid_text_and_language_are_rejected(tmp_path: Path) -> None:
    synth = LocalSpeechSynthesizer(str(tmp_path))
    with pytest.raises(ValueError, match="Unsupported language"):
        await synth.synthesize("Hello", "de")
    with pytest.raises(ValueError, match="Text must contain"):
        await synth.synthesize("  ", "en")
