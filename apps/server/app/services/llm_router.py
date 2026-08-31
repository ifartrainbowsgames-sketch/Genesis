from __future__ import annotations

import httpx

from ..config import settings
from ..schemas import ChatMessage, Provider


class LLMError(RuntimeError):
    pass


class LLMRouter:
    def __init__(self) -> None:
        self.timeout = httpx.Timeout(120.0, connect=10.0)

    def default_model(self, provider: Provider) -> str:
        return {
            "ollama": settings.ollama_chat_model,
            "openai": settings.openai_model,
            "anthropic": settings.anthropic_model,
        }[provider]

    async def chat(self, provider: Provider, messages: list[ChatMessage], model: str | None = None) -> tuple[str, str]:
        model_name = model or self.default_model(provider)
        if provider == "ollama":
            return model_name, await self._ollama(messages, model_name)
        if provider == "openai":
            return model_name, await self._openai(messages, model_name)
        if provider == "anthropic":
            return model_name, await self._anthropic(messages, model_name)
        raise LLMError(f"Unsupported provider: {provider}")

    async def _ollama(self, messages: list[ChatMessage], model: str) -> str:
        payload = {
            "model": model,
            "messages": [m.model_dump() for m in messages],
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{settings.ollama_base_url.rstrip('/')}/api/chat", json=payload)
        if response.is_error:
            raise LLMError(f"Ollama error {response.status_code}: {response.text[:500]}")
        data = response.json()
        try:
            return data["message"]["content"]
        except KeyError as exc:
            raise LLMError(f"Unexpected Ollama response: {data}") from exc

    async def _openai(self, messages: list[ChatMessage], model: str) -> str:
        if not settings.openai_api_key:
            raise LLMError("OPENAI_API_KEY is not configured")
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "input": [m.model_dump() for m in messages],
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post("https://api.openai.com/v1/responses", headers=headers, json=payload)
        if response.is_error:
            raise LLMError(f"OpenAI error {response.status_code}: {response.text[:500]}")
        data = response.json()
        parts: list[str] = []
        for item in data.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    parts.append(content["text"])
        if not parts:
            raise LLMError(f"Unexpected OpenAI response: {str(data)[:800]}")
        return "".join(parts)

    async def _anthropic(self, messages: list[ChatMessage], model: str) -> str:
        if not settings.anthropic_api_key:
            raise LLMError("ANTHROPIC_API_KEY is not configured")

        system_parts = [m.content for m in messages if m.role == "system"]
        body_messages = [m.model_dump() for m in messages if m.role != "system"]
        headers = {
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": model,
            "max_tokens": 4096,
            "messages": body_messages,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload)
        if response.is_error:
            raise LLMError(f"Anthropic error {response.status_code}: {response.text[:500]}")
        data = response.json()
        parts = [item.get("text", "") for item in data.get("content", []) if item.get("type") == "text"]
        return "".join(parts)


router = LLMRouter()
