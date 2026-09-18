import asyncio
from sentence_transformers import SentenceTransformer
from functools import lru_cache

MODEL_NAME = "BAAI/bge-base-en-v1.5"
EMBED_DIM = 768


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)


def _encode(texts: list[str]) -> list[list[float]]:
    model = _get_model()
    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        batch_size=16,
        show_progress_bar=False,
    )
    return vectors.tolist()


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return await asyncio.to_thread(_encode, texts)


async def embed_query(text: str) -> list[float]:
    if not text:
        return [0.0] * EMBED_DIM
    return (await embed_texts([f"query: {text}"]))[0]