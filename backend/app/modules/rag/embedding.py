import asyncio
from collections.abc import Sequence

from fastembed import TextEmbedding

EMBEDDING_DIMENSION = 384


class LocalEmbedder:
    def __init__(self, model_name: str, cache_dir: str) -> None:
        self.model_name = model_name
        self.model = TextEmbedding(model_name=model_name, cache_dir=cache_dir)

    def embed_sync(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = [vector.tolist() for vector in self.model.embed(list(texts), batch_size=16)]
        if any(len(vector) != EMBEDDING_DIMENSION for vector in vectors):
            raise ValueError("Unexpected embedding dimension")
        return vectors

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return await asyncio.to_thread(self.embed_sync, texts)
