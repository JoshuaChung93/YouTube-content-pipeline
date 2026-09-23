from __future__ import annotations


def strip_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    first_break = stripped.find("\n")
    if first_break == -1:
        return stripped
    body = stripped[first_break + 1 :]
    if body.rstrip().endswith("```"):
        body = body.rstrip()[:-3]
    return body.strip()
