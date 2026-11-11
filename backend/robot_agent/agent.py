"""Mock transport for testing the robot audio contract without Unitree hardware."""

import argparse
import asyncio
import base64
import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx


class RobotAudioAgent:
    def __init__(
        self,
        host_url: str,
        robot_id: str,
        api_key: str | None = None,
        timeout_seconds: float = 120,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        parsed = urlparse(host_url)
        if parsed.scheme != "http" or not parsed.hostname:
            raise ValueError("AI host must be an HTTP URL on the trusted local network")
        if not robot_id or len(robot_id) > 64:
            raise ValueError("Invalid robot identity")
        self.host_url = host_url.rstrip("/")
        self.robot_id = robot_id
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def ask(self, wav: bytes, language: str | None = None) -> tuple[str, bytes]:
        if not wav.startswith(b"RIFF") or len(wav) > 10_000_000:
            raise ValueError("Expected WAV audio of at most 10 MB")
        headers = {"Content-Type": "audio/wav", "X-Robot-ID": self.robot_id}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        params = {"idempotency_key": str(uuid4())}
        if language:
            params["language"] = language
        async with httpx.AsyncClient(
            timeout=self.timeout_seconds, transport=self.transport
        ) as client:
            for attempt in range(3):
                try:
                    response = await client.post(
                        self.host_url + "/api/v1/dialog/audio",
                        content=wav,
                        headers=headers,
                        params=params,
                    )
                except httpx.TransportError:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(0.2 * (2**attempt))
                    continue
                if response.status_code in (502, 503, 504) and attempt < 2:
                    await asyncio.sleep(0.2 * (2**attempt))
                    continue
                break
            response.raise_for_status()
            payload = response.json()
        return payload["answer"]["answer"], base64.b64decode(
            payload["audio_wav_base64"], validate=True
        )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Mock robot WAV input/output")
    parser.add_argument("--host", required=True)
    parser.add_argument("--robot-id", required=True)
    parser.add_argument("--input-wav", type=Path, required=True)
    parser.add_argument("--output-wav", type=Path, required=True)
    parser.add_argument("--language", choices=("kk", "ru", "en"))
    args = parser.parse_args()
    answer, audio = await RobotAudioAgent(
        args.host, args.robot_id, os.getenv("ROBOT_LLM_API_KEY")
    ).ask(args.input_wav.read_bytes(), args.language)
    args.output_wav.write_bytes(audio)
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())
