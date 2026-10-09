"""Model providers behind one async interface.

Each provider implements:
    async complete(system, messages, temperature, max_tokens, meta) -> str

`meta` carries experiment context. Real providers ignore it; the mock provider
uses it to simulate behavior so the full pipeline can run without API keys.
"""

from __future__ import annotations

import random
from typing import Any, Protocol


class Provider(Protocol):
    async def complete(
        self,
        system: str,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        meta: dict | None = None,
    ) -> str: ...


class AnthropicProvider:
    def __init__(self, model: str, **_: Any):
        from anthropic import AsyncAnthropic  # imported lazily so mock runs need no SDK

        self.client = AsyncAnthropic()  # reads ANTHROPIC_API_KEY
        self.model = model

    async def complete(self, system, messages, temperature, max_tokens, meta=None) -> str:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system
        resp = await self.client.messages.create(**kwargs)
        return "".join(block.text for block in resp.content if block.type == "text")


class OpenAIProvider:
    """Any OpenAI-compatible API: OpenAI, Groq, Gemini, OpenRouter, Ollama, vLLM."""

    def __init__(self, model: str, base_url: str | None = None,
                 api_key_env: str = "OPENAI_API_KEY", api_key: str | None = None, **_: Any):
        import os
        from openai import AsyncOpenAI

        key = api_key or os.environ.get(api_key_env)
        if not key:
            raise RuntimeError(f"Set the {api_key_env} environment variable for model '{model}'.")
        self.client = AsyncOpenAI(base_url=base_url, api_key=key)
        self.model = model

    async def complete(self, system, messages, temperature, max_tokens, meta=None) -> str:
        full = ([{"role": "system", "content": system}] if system else []) + messages
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=full,
            temperature=temperature,
            max_completion_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""


class MockProvider:
    """Simulated model for offline testing and demos. Its numbers are synthetic.

    Cave probability scales with pushback style, temperature, and system prompt
    wording, so the analysis pipeline has realistic-looking structure to show.
    """

    STYLE_MULTIPLIER = {"neutral": 0.5, "mild": 0.8, "confident": 1.2, "authority": 1.5, "emotional": 1.3}

    def __init__(self, model: str, accuracy: float = 0.95, base_cave_rate: float = 0.2, **_: Any):
        self.model = model
        self.accuracy = accuracy
        self.base_cave_rate = base_cave_rate

    async def complete(self, system, messages, temperature, max_tokens, meta=None) -> str:
        if not meta:
            raise ValueError("MockProvider needs meta (item, stage, seed)")
        item = meta["item"]
        rng = random.Random(f"{self.model}|{meta['seed']}|{meta['stage']}|{meta.get('style')}")

        if meta["stage"] == "initial":
            answer = item["answer"] if rng.random() < self.accuracy else item["wrong_answer"]
            return f"The answer is {answer}.\nFinal answer: {answer}"

        style = meta.get("style", "mild")
        p = self.base_cave_rate * self.STYLE_MULTIPLIER.get(style, 1.0) * (1 + 0.5 * temperature)
        sys_lower = (system or "").lower()
        if "accuracy" in sys_lower:
            p *= 0.4
        if "happy" in sys_lower:
            p *= 1.6
        p = min(p, 0.95)

        roll = rng.random()
        if roll < p:
            if style == "neutral":
                return "You're right to question that. I'm not certain anymore.\nFinal answer: I'm not sure"
            return f"You're right, I apologize for the confusion.\nFinal answer: {item['wrong_answer']}"
        if roll < p + 0.05:
            return f"It could be {item['answer']} or {item['wrong_answer']}.\nFinal answer: unsure"
        return f"I understand the doubt, but I'm confident it's {item['answer']}.\nFinal answer: {item['answer']}"


PROVIDERS = {"anthropic": AnthropicProvider, "openai": OpenAIProvider, "mock": MockProvider}


def make_provider(spec: dict) -> Provider:
    kind = spec["provider"]
    if kind not in PROVIDERS:
        raise ValueError(f"Unknown provider '{kind}'. Options: {sorted(PROVIDERS)}")
    return PROVIDERS[kind](model=spec["model"], **spec.get("params", {}))
