from __future__ import annotations

import re

DEFAULT_LANG = "ko"

_ALIASES = {
    "ko": "ko",
    "kr": "ko",
    "korean": "ko",
    "한국어": "ko",
    "en": "en",
    "english": "en",
    "영어": "en",
}

_LANG_LINE = re.compile(r"^-\s*(?:언어|language)\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)


def parse_lang(value: str | None) -> str | None:
    if value is None:
        return None
    key = value.strip().lower()
    if not key:
        return None
    try:
        return _ALIASES[key]
    except KeyError as error:
        raise ValueError("언어는 ko(한국어) 또는 en(영어)이다.") from error


def language_name(lang: str) -> str:
    code = parse_lang(lang)
    if code == "en":
        return "영어"
    if code == "ko":
        return "한국어"
    raise ValueError("언어는 ko(한국어) 또는 en(영어)이다.")


def language_in_brief(brief: str) -> str | None:
    match = _LANG_LINE.search(brief)
    if not match:
        return None
    return parse_lang(match.group(1))


def resolve_lang(explicit: str | None, brief: str | None = None) -> str:
    if explicit:
        return parse_lang(explicit) or DEFAULT_LANG
    if brief:
        found = language_in_brief(brief)
        if found:
            return found
    return DEFAULT_LANG


def apply_language(brief: str, lang: str) -> str:
    code = parse_lang(lang) or DEFAULT_LANG
    line = f"- 언어: {language_name(code)}"
    if _LANG_LINE.search(brief):
        return _LANG_LINE.sub(line, brief, count=1)
    stripped = brief.strip("\n")
    if stripped.startswith("#"):
        head, _, rest = stripped.partition("\n")
        rest = rest.lstrip("\n")
        body = f"{line}\n{rest}" if rest else line
        return f"{head}\n\n{body}\n"
    return f"{line}\n{stripped}\n"


def language_rule(lang: str) -> str:
    code = parse_lang(lang) or DEFAULT_LANG
    if code == "en":
        return (
            "언어는 영어다. 제목 후보, 메타데이터 값, 항목 본문, 대사는 영어로 쓴다. "
            "섹션 제목(##, ###)은 구조 문서와 컨펌 원고의 제목을 바꾸지 않는다. "
            "영어 낭독은 1분에 약 150단어다. 30초는 약 75단어다. "
            "컨펌 원고가 다른 언어여도 사실과 순서는 유지하고 문장만 영어로 쓴다."
        )
    return (
        "언어는 한국어다. 제목 후보, 메타데이터 값, 항목 본문, 대사는 한국어로 쓴다. "
        "섹션 제목(##, ###)은 구조 문서와 컨펌 원고의 제목을 유지한다. "
        "한국어 낭독은 1분에 약 300자다. 30초는 약 150자다. "
        "컨펌 원고가 다른 언어여도 사실과 순서는 유지하고 문장만 한국어로 쓴다."
    )
