import httpx

from app.config import settings

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

MODELS = {
    "extract": "openai/gpt-oss-20b",
    "score": "qwen/qwen3.6-27b",
    "reason": "qwen/qwen3.8-27b",
    "cover_letter": "groq/compound-mini",
    "comp": "groq/compound",
    "resume_optimize": "openai/gpt-oss-120b",
}


class GroqError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


async def call_groq(role: str, messages: list[dict], max_tokens: int = 1024, temperature: float = 0.2) -> str:
    model = MODELS[role]
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(GROQ_URL, json=payload, headers=headers)

    if resp.status_code in (429, 503):
        raise GroqError(resp.status_code, resp.text)
    resp.raise_for_status()

    data = resp.json()
    return data["choices"][0]["message"]["content"]