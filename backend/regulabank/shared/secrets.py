"""La clave de OpenAI: OPENAI_API_KEY o el llavero de macOS (servicio `lumen-openai`). Nunca se escribe en archivos ni en el log."""

from __future__ import annotations

import os
import subprocess


class NoKey(RuntimeError):
    pass


def api_key() -> str:
    k = os.environ.get("OPENAI_API_KEY")
    if k:
        return k
    r = subprocess.run(["security", "find-generic-password", "-s", "lumen-openai", "-w"], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        raise NoKey("falta la clave: exporta OPENAI_API_KEY o guarda el servicio `lumen-openai` en el llavero")
    return r.stdout.strip()
