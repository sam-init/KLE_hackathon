from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from backend.utils.settings import settings

logger = logging.getLogger(__name__)

# Conservative timeout for Render free-tier: NIM must respond within 120 s or we skip.
_NIM_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=5.0)
_NIM_MAX_RETRIES = 3


class NIMClient:
    def __init__(self) -> None:
        # Normalise: strip trailing slash, then strip accidental trailing /v1
        # so we can safely append /v1/chat/completions ourselves.
        base = settings.nim_base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        self.base_url = base
        self.api_key = settings.nim_api_key

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def chat(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
    ) -> str | None:
        if not self.enabled:
            logger.info("NIM disabled (missing API key) | model=%s", model)
            return None

        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            # Keep this moderate to reduce Render/NIM timeout and limit pressure.
            "max_tokens": 2048,
        }

        async with httpx.AsyncClient(timeout=_NIM_TIMEOUT) as client:
            for attempt in range(1, _NIM_MAX_RETRIES + 1):
                started = time.perf_counter()
                logger.info("NIM request started | model=%s attempt=%d/%d", model, attempt, _NIM_MAX_RETRIES)
                try:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    elapsed_ms = int((time.perf_counter() - started) * 1000)
                    logger.info("NIM request succeeded | model=%s attempt=%d elapsed_ms=%d", model, attempt, elapsed_ms)
                    return data["choices"][0]["message"]["content"]
                except httpx.TimeoutException as exc:
                    elapsed_ms = int((time.perf_counter() - started) * 1000)
                    logger.warning(
                        "NIM timeout for model %s (attempt %d/%d) elapsed_ms=%d: %s",
                        model,
                        attempt,
                        _NIM_MAX_RETRIES,
                        elapsed_ms,
                        exc,
                    )
                except httpx.HTTPStatusError as exc:
                    elapsed_ms = int((time.perf_counter() - started) * 1000)
                    status = exc.response.status_code
                    body = exc.response.text[:300]
                    logger.warning(
                        "NIM HTTP error %s for model %s (attempt %d/%d) elapsed_ms=%d: %s",
                        status,
                        model,
                        attempt,
                        _NIM_MAX_RETRIES,
                        elapsed_ms,
                        body,
                    )
                    # Retry rate-limited and transient upstream failures.
                    if status not in {429, 500, 502, 503, 504}:
                        logger.warning("NIM request aborted (non-retriable status) | model=%s status=%s", model, status)
                        return None
                except Exception as exc:
                    logger.warning("NIM call failed for model %s: %s", model, exc)
                    return None

                if attempt < _NIM_MAX_RETRIES:
                    logger.info("NIM retry scheduled | model=%s next_attempt=%d", model, attempt + 1)
                    await asyncio.sleep(attempt * 2)

        logger.warning("NIM request exhausted retries | model=%s", model)
        return None
