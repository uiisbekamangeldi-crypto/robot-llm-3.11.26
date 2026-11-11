import asyncio
from urllib.parse import urlparse

import httpx


class LocalLLM:
    def __init__(self, url: str, model: str, timeout_seconds: float = 45.0) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "llm"}:
            raise ValueError("LLM URL must use loopback or the private Compose service")
        self.url = url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._semaphore = asyncio.Semaphore(1)

    async def generate(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.0,
            "max_tokens": 200,
            "stream": False,
        }
        async with self._semaphore:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(f"{self.url}/v1/chat/completions", json=payload)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("Local LLM returned empty content")
                return content.strip()
