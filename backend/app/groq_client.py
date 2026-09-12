import httpx

from app.config import settings

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

MODELS = {
    "extract": "qwen/qwen3.6-27b",
    "score_reason": "qwen/qwen3.8-27b",
    "comp": "openai/gpt-oss-20b",
    "resume_optimize": "openai/gpt-oss-120b",
    "resume_review": "allam-2-7b",
    "resume_verify": "allam-2-7b",
}

class GroqError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


async def call_groq(role: str, messages: list[dict], max_tokens: int = 1024, temperature: float = 0.2, reasoning_effort: str | None = None) -> str:
    model = MODELS[role]
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(GROQ_URL, json=payload, headers=headers)

    if resp.status_code in (429, 503, 413, 400):
        raise GroqError(resp.status_code, resp.text)
    resp.raise_for_status()

    data = resp.json()
    return data["choices"][0]["message"]["content"]

async def call_groq_with_tools(role: str, messages: list[dict], tools: list[dict], max_tokens: int = 1024) -> dict:
    model = MODELS[role]
    payload = {"model": model, "messages": messages, "tools": tools, "max_tokens": max_tokens, "temperature": 0.2}
    headers = {"Authorization": f"Bearer {settings.groq_api_key}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(GROQ_URL, json=payload, headers=headers)

    if resp.status_code in (429, 503, 413, 400):
        raise GroqError(resp.status_code, resp.text)
    resp.raise_for_status()

    data = resp.json()
    return data["choices"][0]["message"]