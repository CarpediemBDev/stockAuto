import json
from typing import Any

import httpx

from app.core.config import settings


DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
DEFAULT_GEMINI_TIMEOUT_SECONDS = 8.0


class GeminiClientError(RuntimeError):
    pass


class GeminiClient:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_GEMINI_MODEL,
        timeout_seconds: float = DEFAULT_GEMINI_TIMEOUT_SECONDS,
    ):
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.model = model
        self.timeout_seconds = timeout_seconds

    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key != "your_gemini_api_key_here")

    async def generate_json(self, prompt: str) -> dict[str, Any]:
        if not self.is_configured():
            raise GeminiClientError("Gemini API key is not configured.")

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
        except httpx.HTTPError as exc:
            raise GeminiClientError(f"Gemini request failed: {exc}") from exc

        if response.status_code != 200:
            raise GeminiClientError(
                f"Gemini API failed with status {response.status_code}: {response.text[:300]}"
            )

        try:
            data = response.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            return json.loads(_strip_markdown_fence(raw_text))
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GeminiClientError("Gemini response did not contain valid JSON.") from exc


def _strip_markdown_fence(raw_text: str) -> str:
    if not raw_text.startswith("```"):
        return raw_text

    lines = raw_text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()
