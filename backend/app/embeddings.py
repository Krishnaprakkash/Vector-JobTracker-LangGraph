from sentence_transformers import SentenceTransformer
from functools import lru_cache
import numpy as np

MODEL_NAME = "BAAI/bge-base-en-v1.5"
EMBED_DIM = 768


@lru_cache(maxsize=1)
def _get_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME)


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    model = _get_model()
    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        batch_size=16,
        show_progress_bar=False,
    )
    return vectors.tolist()


def embed_query(text: str) -> list[float]:
    return embed_texts([f"query: {text}"])[0] if text else [0.0] * EMBED_DIM