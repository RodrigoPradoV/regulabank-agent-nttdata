"""Captura bronze: baja cada source_url con httpx (o acepta una ruta local) y registra sha256.

Ritmo: pausa entre peticiones, timeout de 30 s, se frena al primer 403 y se informa. Nunca se vuelve a bajar
un archivo que ya esta en bronze. El original no se modifica jamas (docs/02-corpus.md).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from regulabank.corpus.norms import Norm

log = logging.getLogger(__name__)

KNOWN_EXT = ("pdf", "md", "txt", "html", "htm", "doc", "docx")
CONTENT_TYPE_EXT = {
    "application/pdf": "pdf",
    "text/markdown": "md",
    "text/plain": "txt",
    "text/html": "html",
    "application/msword": "doc",
}


@dataclass
class Capture:
    """Resultado por norma: ruta en bronze (o local), sha256 y como se obtuvo."""

    norm_id: str
    path: Path | None
    sha256: str | None
    outcome: str  # local | downloaded | cached | blocked_403 | skipped_after_403 | missing | error:<detalle>

    @property
    def ok(self) -> bool:
        return self.path is not None and self.sha256 is not None


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _ext_from_url(url: str) -> str | None:
    name = unquote(urlparse(url).path).rsplit("/", 1)[-1].lower()
    if "." in name:
        ext = name.rsplit(".", 1)[-1]
        if ext in KNOWN_EXT:
            return ext
    return None


def _existing(bronze_dir: Path, norm_id: str) -> Path | None:
    for ext in KNOWN_EXT:
        p = bronze_dir / f"{norm_id}.{ext}"
        if p.exists():
            return p
    return None


def _write_sidecar(path: Path, norm: Norm, sha: str, outcome: str) -> None:
    meta = {
        "norm_id": norm.norm_id,
        "source_url": norm.source_url,
        "file": path.name,
        "sha256": sha,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "outcome": outcome,
    }
    path.with_suffix(path.suffix + ".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))


def capture_all(
    norms: list[Norm],
    bronze_dir: Path,
    user_agent: str,
    sleep_s: float = 5.0,
    timeout_s: float = 30.0,
) -> list[Capture]:
    """Resuelve la fuente de cada norma. Devuelve una Capture por norma, en el mismo orden."""
    bronze_dir.mkdir(parents=True, exist_ok=True)
    results: list[Capture] = []
    blocked = False
    requests_made = 0
    client = httpx.Client(headers={"User-Agent": user_agent}, timeout=timeout_s, follow_redirects=True)
    try:
        for norm in norms:
            if norm.source_path:
                local = Path(norm.source_path)
                if local.exists():
                    results.append(Capture(norm.norm_id, local, sha256_of(local), "local"))
                else:
                    results.append(Capture(norm.norm_id, None, None, f"error:no existe {local}"))
                continue
            cached = _existing(bronze_dir, norm.norm_id)
            if cached is not None:
                results.append(Capture(norm.norm_id, cached, sha256_of(cached), "cached"))
                continue
            if not norm.source_url:
                results.append(Capture(norm.norm_id, None, None, "missing"))
                continue
            if blocked:
                results.append(Capture(norm.norm_id, None, None, "skipped_after_403"))
                continue
            if requests_made:
                time.sleep(sleep_s)
            requests_made += 1
            try:
                resp = client.get(norm.source_url)
            except httpx.HTTPError as exc:
                results.append(Capture(norm.norm_id, None, None, f"error:{type(exc).__name__}"))
                continue
            if resp.status_code == 403:
                blocked = True
                log.warning("403 en %s; se frena la captura", norm.source_url)
                results.append(Capture(norm.norm_id, None, None, "blocked_403"))
                continue
            if resp.status_code != 200:
                results.append(Capture(norm.norm_id, None, None, f"error:http {resp.status_code}"))
                continue
            ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            ext = _ext_from_url(norm.source_url) or CONTENT_TYPE_EXT.get(ctype)
            if resp.content[:4] == b"%PDF":
                ext = "pdf"
            if ext is None:
                results.append(Capture(norm.norm_id, None, None, f"error:tipo desconocido {ctype}"))
                continue
            target = bronze_dir / f"{norm.norm_id}.{ext}"
            target.write_bytes(resp.content)
            sha = sha256_of(target)
            _write_sidecar(target, norm, sha, "downloaded")
            results.append(Capture(norm.norm_id, target, sha, "downloaded"))
    finally:
        client.close()
    return results
