from __future__ import annotations

from ytpipe.language import language_rule

GENERATE_INSTRUCTIONS = """당신은 유튜브 영상의 2차 컨펌용 원고를 쓴다.
아래 구조 문서가 섹션 순서, 분량, 출력 형식의 기준이다. 문서에 없는 최상위 섹션을 만들지 않는다.
각 항목은 구조 문서의 줄 수 제한을 지킨다. 낭독 대본으로 늘리지 않는다.
채널 말투 문서에서 값이 채워진 항목만 반영한다. 빈 칸으로 화자를 지어내지 않는다.
참고 스크립트가 있으면 문장 호흡과 섹션을 넘기는 방식만 보고, 그 안의 사실과 문장은 가져오지 않는다.
브리프에 없는 수치, 연구, 개인 경험, 고유명사를 만들지 않는다.
출력은 구조 문서의 출력 형식 그대로다. 코드 펜스와 편집 메모는 붙이지 않는다."""

NARRATE_INSTRUCTIONS = """당신은 컨펌이 끝난 원고를 낭독용 대본으로 푼다.
아래 낭독 문서가 분량, 말하는 순서, 출력 형식의 기준이다.
컨펌 원고에 있는 섹션, 순서, 주장, 과제 유무가 기준이다. 원고에 없는 섹션, 개념, 수치, 연구, 개인 경험, 고유명사를 만들지 않는다.
브리프의 "넣지 말 것"은 지킨다. 브리프와 원고가 다르면 컨펌 원고를 따른다.
채널 말투 문서에서 값이 채워진 항목만 반영한다. 빈 칸으로 화자를 지어내지 않는다.
참고 대본이 있으면 문장 호흡과 섹션을 넘기는 방식만 보고, 그 안의 사실과 문장은 가져오지 않는다.
항목 라벨을 소리 내어 읽지 않는다. 코드 펜스와 편집 메모는 붙이지 않는다.
문장을 사람이 말한 것처럼 다듬는 일은 다음 단계가 한다."""

_HUMANIZE_CONTEXTS = {
    "confirm": """이 글은 2차 컨펌용 원고다. 글머리 항목과 각 항목 3줄 이내 요약을 유지한다. 낭독 대본으로 늘리지 않는다.
섹션 제목, 순서, 사실, 숫자, 고유명사, 주장의 강도는 유지한다.
원고에 없는 경험, 근거, 인용을 넣지 않는다. 섹션을 합치거나 순서를 바꾸지 않는다.""",
    "narration": """이 글은 카메라 앞에서 소리 내어 읽는 낭독 대본이다.
섹션 제목과 순서, 타임스탬프, `[화면: ...]` 표기, 사실, 숫자, 고유명사, 주장의 강도는 유지한다.
대본에 없는 경험, 근거, 인용을 넣지 않는다. 섹션을 합치거나 순서를 바꾸지 않는다.""",
}

HUMANIZE_INSTRUCTIONS = """아래 편집 가이드를 rewrite 모드로 적용해 유튜브 원고를 다듬어라.
가이드에 따로 적힌 voice 변환은 요청하지 않는다. 초안의 언어와 태도를 유지한다.
{context}
가이드를 어떻게 적용했는지 설명하지 말고, 다듬은 스크립트만 출력한다."""


def generate_messages(
    *,
    structure: str,
    channel: str,
    examples: list[tuple[str, str]],
    brief: str,
    lang: str = "ko",
) -> list[dict[str, str]]:
    parts = [
        GENERATE_INSTRUCTIONS,
        language_rule(lang),
        "",
        "# 구조 문서",
        structure,
        "",
        "# 채널 말투",
        channel,
    ]
    if examples:
        parts.extend(["", "# 참고 스크립트", "말의 결만 참고한다."])
        for name, text in examples:
            parts.extend(["", f"## {name}", text])
    else:
        parts.extend(["", "# 참고 스크립트", "아직 없다."])
    return [
        {"role": "system", "content": "\n".join(parts)},
        {"role": "user", "content": brief.strip()},
    ]


def narrate_messages(
    *,
    narration: str,
    channel: str,
    examples: list[tuple[str, str]],
    confirmed: str,
    brief: str,
    lang: str = "ko",
) -> list[dict[str, str]]:
    parts = [
        NARRATE_INSTRUCTIONS,
        language_rule(lang),
        "",
        "# 낭독 문서",
        narration,
        "",
        "# 채널 말투",
        channel,
    ]
    if examples:
        parts.extend(["", "# 참고 대본", "말의 결만 참고한다."])
        for name, text in examples:
            parts.extend(["", f"## {name}", text])
    else:
        parts.extend(["", "# 참고 대본", "아직 없다."])
    user = "\n".join(
        [
            "# 컨펌 원고",
            confirmed.strip(),
            "",
            "# 브리프",
            brief.strip(),
        ]
    )
    return [
        {"role": "system", "content": "\n".join(parts)},
        {"role": "user", "content": user},
    ]


def humanize_messages(
    *,
    guide: str,
    draft: str,
    kind: str = "confirm",
    lang: str = "ko",
) -> list[dict[str, str]]:
    try:
        context = _HUMANIZE_CONTEXTS[kind]
    except KeyError as error:
        raise ValueError(f"알 수 없는 다듬기 종류: {kind}") from error
    system = (
        HUMANIZE_INSTRUCTIONS.format(context=context)
        + "\n"
        + language_rule(lang)
        + "\n다른 언어로 옮기지 않는다."
        + "\n\n# 편집 가이드\n\n"
        + guide
        + "\n\n# 출력\n다듬은 스크립트만 출력한다. 감사 목록이나 변경 요약은 붙이지 않는다."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": draft.strip()},
    ]
