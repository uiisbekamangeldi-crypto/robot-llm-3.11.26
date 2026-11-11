import base64

import httpx
import pytest

from robot_agent.agent import RobotAudioAgent


@pytest.mark.asyncio
async def test_mock_agent_sends_identity_and_receives_audio() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Robot-ID"] == "g1-test"
        assert request.headers["X-API-Key"] == "test-key"
        assert request.url.path == "/api/v1/dialog/audio"
        assert request.url.params["language"] == "en"
        return httpx.Response(
            200,
            json={
                "answer": {"answer": "Verified answer"},
                "audio_wav_base64": base64.b64encode(b"RIFFtest").decode(),
            },
        )

    agent = RobotAudioAgent(
        "http://127.0.0.1:8000", "g1-test", "test-key", transport=httpx.MockTransport(handler)
    )
    answer, audio = await agent.ask(b"RIFFinput", "en")
    assert answer == "Verified answer"
    assert audio == b"RIFFtest"


@pytest.mark.asyncio
async def test_mock_agent_rejects_non_wav() -> None:
    agent = RobotAudioAgent("http://127.0.0.1:8000", "g1-test")
    with pytest.raises(ValueError, match="Expected WAV"):
        await agent.ask(b"bad")


@pytest.mark.asyncio
async def test_mock_agent_surfaces_host_failure() -> None:
    keys: list[str] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        keys.append(_request.url.params["idempotency_key"])
        return httpx.Response(503, json={"error": "offline"})

    agent = RobotAudioAgent(
        "http://127.0.0.1:8000", "g1-test", transport=httpx.MockTransport(handler)
    )
    with pytest.raises(httpx.HTTPStatusError):
        await agent.ask(b"RIFFinput", "ru")
    assert len(keys) == 3
    assert len(set(keys)) == 1
