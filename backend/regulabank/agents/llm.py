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

API = "https://api.openai.com/v1"
PREFERRED = ("gpt-5-mini", "gpt-5", "gpt-4.1-mini", "gpt-4o-mini")
# USD por millon de tokens (entrada, salida). Estimado: revisar la tabla de precios vigente.
PRICE = {"gpt-5-mini": (0.25, 2.00), "gpt-5": (1.25, 10.00), "gpt-4.1-mini": (0.40, 1.60), "gpt-4o-mini": (0.15, 0.60)}


class NoKey(RuntimeError):
    pass


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


class Provider(Protocol):
    name: str

    def complete(self, system: str, user: str, prompt_version: str) -> Reply: ...


def api_key() -> str:
    k = os.environ.get("OPENAI_API_KEY")
    if k:
        return k
    r = subprocess.run(["security", "find-generic-password", "-s", "lumen-openai", "-w"], capture_output=True,
                       text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise NoKey("falta la clave: exporta OPENAI_API_KEY o guarda el servicio `lumen-openai` en el llavero")
    return r.stdout.strip()


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


@dataclass
class FakeProvider:
    """Respuestas guionadas: una cola de textos; sin cola, cita [1] con el inicio del primer pasaje."""

    script: list[str] = field(default_factory=list)
    name: str = "fake"
    calls: list[tuple[str, str]] = field(default_factory=list)

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
