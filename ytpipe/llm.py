from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from ytpipe.textutil import strip_fences


class LLMError(Exception):
    pass


def require_settings() -> tuple[str, str, str]:
    api_key = os.environ.get("YTPIPE_API_KEY", "").strip()
    base_url = os.environ.get("YTPIPE_BASE_URL", "https://api.openai.com/v1").strip()
    model = os.environ.get("YTPIPE_MODEL", "").strip()
    missing = []
    if not api_key:
        missing.append("YTPIPE_API_KEY")
    if not model:
        missing.append("YTPIPE_MODEL")
    if missing:
        names = ", ".join(missing)
        raise LLMError(f".env에 {names}가 필요하다. 예시는 .env.example 이다.")
    return api_key, base_url.rstrip("/"), model


def locks_temperature(model: str) -> bool:
    """gpt-6-luna는 temperature 기본값만 받는다."""
    return "gpt-6-luna" in model.lower()


def temperature_was_rejected(status: int, detail: str) -> bool:
    if status != 400:
        return False
    try:
        body = json.loads(detail)
    except json.JSONDecodeError:
        body = None
    error = body.get("error") if isinstance(body, dict) else None
    if isinstance(error, dict) and error.get("param") == "temperature":
        return True
    text = detail.lower()
    return "temperature" in text and "support" in text


def request_body(
    model: str,
    messages: list[dict[str, str]],
    temperature: float | None,
) -> dict[str, object]:
    body: dict[str, object] = {"model": model, "messages": messages}
    if temperature is not None:
        body["temperature"] = temperature
    return body


def complete(messages: list[dict[str, str]], *, temperature: float) -> str:
    api_key, base_url, model = require_settings()
    requested = None if locks_temperature(model) else temperature
    try:
        raw = _post(api_key, base_url, request_body(model, messages, requested))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        if requested is not None and temperature_was_rejected(error.code, detail):
            try:
                raw = _post(api_key, base_url, request_body(model, messages, None))
            except urllib.error.HTTPError as retry_error:
                retry_detail = retry_error.read().decode("utf-8", errors="replace")[:500]
                raise LLMError(
                    f"모델 호출이 실패했다 ({retry_error.code}): {retry_detail}"
                ) from retry_error
        else:
            raise LLMError(f"모델 호출이 실패했다 ({error.code}): {detail}") from error
    except urllib.error.URLError as error:
        raise LLMError(f"모델 서버에 연결하지 못했다: {error.reason}") from error

    try:
        body = json.loads(raw)
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
        raise LLMError("모델 응답에서 스크립트를 읽지 못했다.") from error

    if isinstance(content, list):
        texts = []
        for part in content:
            if isinstance(part, dict):
                texts.append(str(part.get("text", "")))
            else:
                texts.append(str(part))
        content = "".join(texts)
    if not isinstance(content, str) or not content.strip():
        raise LLMError("모델이 빈 스크립트를 반환했다.")
    return strip_fences(content)


def _post(api_key: str, base_url: str, body: dict[str, object]) -> str:
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read().decode("utf-8")
