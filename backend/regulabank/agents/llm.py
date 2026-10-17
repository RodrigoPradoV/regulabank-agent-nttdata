"""Proveedores del nodo `answer`: OpenAI (gpt-5-mini, como lumen) y uno falso para pruebas.

Mismo patron que lumen (microservices/lumen/eval/answer.py): cliente httpx, `chat/completions`, el modelo cita
cada afirmacion con [n] y el codigo verifica esas citas. La clave sale de OPENAI_API_KEY o del llavero de macOS
(servicio `lumen-openai`); nunca se escribe en archivos ni en el log.

`MODEL_PROVIDER=mock` usa FakeProvider (el flujo completo corre sin gastar). Las respuestas se guardan por
contenido (sha del modelo + mensajes + version del prompt) y no se vuelven a pagar.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import httpx

from regulabank.shared.secrets import NoKey, api_key  # noqa: F401 - se reexportan: otros modulos los importan de aqui
from typing import Any

API = "https://api.openai.com/v1"
PREFERRED = ("gpt-5-mini", "gpt-5", "gpt-4.1-mini", "gpt-4o-mini")
CHOICES = ("gpt-5-mini", "gpt-5")   # lo que el agente puede elegir: barato por defecto, potente si la tarea lo pide
# USD por millon de tokens (entrada, salida). Estimado: revisar la tabla de precios vigente.
PRICE = {"gpt-5-mini": (0.25, 2.00), "gpt-5": (1.25, 10.00), "gpt-4.1-mini": (0.40, 1.60), "gpt-4o-mini": (0.15, 0.60)}


@dataclass
class Reply:
    text: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    cached: bool = False
    finish_reason: str | None = None


@dataclass
class ChatReply:
    """Un turno del modelo con herramientas: el mensaje del asistente (texto y/o tool_calls) y su costo."""

    message: dict
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    cached: bool = False
    finish_reason: str | None = None


class Provider(Protocol):
    name: str

    def complete(self, system: str, user: str, prompt_version: str) -> Reply: ...

    def chat(self, messages: list[dict], tools: list[dict] | None, prompt_version: str, model: str | None = None,
             tool_choice: Any = None) -> ChatReply: ...

    def models(self) -> list[str]: ...


def cost(model: str, tokens_in: int, tokens_out: int) -> float:
    pin, pout = PRICE.get(model, PRICE["gpt-5-mini"])
    return round((tokens_in * pin + tokens_out * pout) / 1e6, 6)


class OpenAIProvider:
    def __init__(self, model: str | None = None, cache_dir: Path | None = None, reasoning_effort: str = "low"):
        self.http = httpx.Client(base_url=API, headers={"Authorization": f"Bearer {api_key()}"}, timeout=90)
        self.model = model or os.environ.get("OPENAI_MODEL") or self._pick()
        self.name = self.model
        self.reasoning_effort = reasoning_effort
        self.cache_dir = cache_dir
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def _pick(self) -> str:
        r = self.http.get("/models")
        r.raise_for_status()
        have = {m["id"] for m in r.json()["data"]}
        for m in PREFERRED:
            if m in have:
                return m
        raise RuntimeError(f"ningun modelo preferido disponible: {sorted(have)[:20]}")

    def complete(self, system: str, user: str, prompt_version: str) -> Reply:
        key = hashlib.sha256(json.dumps([self.model, self.reasoning_effort, system, user, prompt_version],
                                        ensure_ascii=False).encode()).hexdigest()
        path = self.cache_dir / f"{key}.json" if self.cache_dir else None
        if path and path.exists():
            return Reply(**{**json.loads(path.read_text(encoding="utf-8")), "cached": True, "cost_usd": 0.0})
        body: dict = {"model": self.model, "messages": [{"role": "system", "content": system},
                                                        {"role": "user", "content": user}]}
        if self.model.startswith("gpt-5"):
            body["reasoning_effort"] = self.reasoning_effort
        t0 = time.perf_counter()
        r = self.http.post("/chat/completions", json=body)
        if r.status_code != 200:
            raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:300]}")
        d = r.json()
        ch = d["choices"][0]
        usage = d.get("usage", {})
        reply = Reply(text=(ch["message"].get("content") or "").strip(), model=d.get("model", self.model),
                      tokens_in=usage.get("prompt_tokens", 0), tokens_out=usage.get("completion_tokens", 0),
                      cost_usd=cost(self.model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)),
                      latency_ms=round((time.perf_counter() - t0) * 1000), finish_reason=ch.get("finish_reason"))
        if path:
            path.write_text(json.dumps(reply.__dict__, ensure_ascii=False), encoding="utf-8")
        return reply


    def models(self) -> list[str]:
        """Modelos que el agente puede elegir, de menor a mayor potencia, solo los que la cuenta tiene."""
        if not hasattr(self, "_available"):
            r = self.http.get("/models")
            r.raise_for_status()
            have = {m["id"] for m in r.json()["data"]}
            self._available = [m for m in CHOICES if m in have] or [self.model]
        return self._available

    def chat(self, messages: list[dict], tools: list[dict] | None, prompt_version: str, model: str | None = None,
             tool_choice: Any = None) -> ChatReply:
        model = model or self.model
        key = hashlib.sha256(json.dumps([model, self.reasoning_effort, messages, tools, tool_choice, prompt_version],
                                        ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        path = self.cache_dir / f"chat-{key}.json" if self.cache_dir else None
        if path and path.exists():
            return ChatReply(**{**json.loads(path.read_text(encoding="utf-8")), "cached": True, "cost_usd": 0.0})
        body: dict = {"model": model, "messages": messages}
        if tools:
            body["tools"] = tools
            if tool_choice:
                body["tool_choice"] = tool_choice
        if model.startswith("gpt-5"):
            body["reasoning_effort"] = self.reasoning_effort
        t0 = time.perf_counter()
        r = self.http.post("/chat/completions", json=body)
        if r.status_code != 200:
            raise RuntimeError(f"OpenAI {r.status_code}: {r.text[:300]}")
        d = r.json()
        ch = d["choices"][0]
        usage = d.get("usage", {})
        msg = {k: v for k, v in ch["message"].items() if k in ("role", "content", "tool_calls") and v is not None}
        reply = ChatReply(message=msg, model=d.get("model", model), tokens_in=usage.get("prompt_tokens", 0),
                          tokens_out=usage.get("completion_tokens", 0),
                          cost_usd=cost(model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)),
                          latency_ms=round((time.perf_counter() - t0) * 1000), finish_reason=ch.get("finish_reason"))
        if path:
            path.write_text(json.dumps(reply.__dict__, ensure_ascii=False), encoding="utf-8")
        return reply


@dataclass
class FakeProvider:
    """Respuestas guionadas: una cola de textos; sin cola, cita [1] con el inicio del primer pasaje."""

    script: list[str] = field(default_factory=list)
    script_msgs: list[dict] = field(default_factory=list)     # mensajes del asistente para `chat` (con tool_calls)
    name: str = "fake"
    calls: list[tuple[str, str]] = field(default_factory=list)

    def models(self) -> list[str]:
        return ["fake-mini", "fake-strong"]

    def chat(self, messages: list[dict], tools: list[dict] | None, prompt_version: str, model: str | None = None,
             tool_choice: Any = None) -> ChatReply:
        self.calls.append((model or "fake", json.dumps(messages[-1], ensure_ascii=False)))
        msg = self.script_msgs.pop(0) if self.script_msgs else {"role": "assistant", "content": "Según el pasaje [1]."}
        return ChatReply(message=msg, model=model or self.name)

    def complete(self, system: str, user: str, prompt_version: str) -> Reply:
        self.calls.append((system, user))
        text = self.script.pop(0) if self.script else "Según el pasaje [1]."
        return Reply(text=text, model=self.name)


def load_provider(kind: str | None = None, cache_dir: Path | None = None) -> Provider:
    kind = kind or os.environ.get("MODEL_PROVIDER", "mock")
    if kind == "openai":
        return OpenAIProvider(cache_dir=cache_dir)
    if kind == "mock":
        return FakeProvider()
    raise ValueError(f"MODEL_PROVIDER desconocido: {kind} (usa mock u openai)")
