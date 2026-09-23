from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ytpipe.language import resolve_lang
from ytpipe.llm import complete
from ytpipe.loaders import (
    CHANNEL_PATH,
    HUMANIZE_RULE_PATH,
    NARRATION_EXAMPLES_DIR,
    NARRATION_PATH,
    ROOT,
    STRUCTURE_PATH,
    file_record,
    load_channel,
    load_examples,
    load_humanize_guide,
    load_narration,
    load_structure,
    manuscript_headings,
    required_sections,
    structure_problems,
)
from ytpipe.prompts import generate_messages, humanize_messages, narrate_messages

DRAFT_TEMPERATURE = 0.7
NARRATE_TEMPERATURE = 0.7
HUMANIZE_TEMPERATURE = 0.3


@dataclass
class RunResult:
    output_dir: Path
    draft_path: Path | None
    final_path: Path | None
    warnings: list[str]


def build_brief(
    *,
    topic: str,
    audience: str | None = None,
    minutes: int | None = None,
    angle: str | None = None,
    must_include: str | None = None,
    must_avoid: str | None = None,
    cta: str | None = None,
) -> str:
    def value(text: str | None, fallback: str = "지정하지 않음") -> str:
        cleaned = (text or "").strip()
        return cleaned or fallback

    length = f"{minutes}분" if minutes else "지정하지 않음"
    lines = [
        "# 브리프",
        "",
        f"- 주제: {value(topic, '')}",
        f"- 시청자: {value(audience)}",
        f"- 목표 길이: {length}",
        f"- 각도: {value(angle)}",
        f"- 꼭 넣을 내용: {value(must_include)}",
        f"- 넣지 말 것: {value(must_avoid)}",
        f"- 마무리 행동: {value(cta)}",
        "",
    ]
    return "\n".join(lines)


def _warn(script: str, sections: list[str], label: str) -> list[str]:
    return [f"{label}: {problem}" for problem in structure_problems(script, sections)]


def run(
    *,
    brief: str,
    stage: str = "all",
    draft: str | None = None,
    output_root: Path | None = None,
) -> RunResult:
    if stage not in {"all", "draft", "humanize"}:
        raise ValueError(f"알 수 없는 단계: {stage}")
    if stage == "humanize" and not (draft and draft.strip()):
        raise ValueError("humanize 단계에는 초안이 필요하다")

    structure = load_structure()
    sections = required_sections(structure)
    channel = load_channel()
    examples = load_examples()
    warnings: list[str] = []
    lang = resolve_lang(None, brief)

    draft_text = draft.strip() if draft else None
    final_text = None

    if stage in {"all", "draft"}:
        messages = generate_messages(
            structure=structure,
            channel=channel,
            examples=[(path.name, text) for path, text in examples],
            brief=brief,
            lang=lang,
        )
        draft_text = complete(messages, temperature=DRAFT_TEMPERATURE)
        warnings.extend(_warn(draft_text, sections, "초안"))

    if stage in {"all", "humanize"}:
        if not draft_text:
            raise ValueError("humanize 단계에는 초안이 필요하다")
        messages = humanize_messages(
            guide=load_humanize_guide(),
            draft=draft_text,
            kind="confirm",
            lang=lang,
        )
        final_text = complete(messages, temperature=HUMANIZE_TEMPERATURE)
        warnings.extend(_warn(final_text, sections, "최종본"))

    destination = _write_run(
        brief=brief,
        draft=draft_text,
        final=final_text,
        examples=examples,
        output_root=output_root or (ROOT / "output"),
        stage=stage,
    )
    return RunResult(
        output_dir=destination,
        draft_path=destination / "draft.md" if draft_text else None,
        final_path=destination / "final.md" if final_text else None,
        warnings=warnings,
    )


def narrate(
    *,
    confirmed: str,
    brief: str,
    stage: str = "all",
    draft: str | None = None,
    confirmed_path: Path | None = None,
    output_root: Path | None = None,
) -> RunResult:
    if stage not in {"all", "draft", "humanize"}:
        raise ValueError(f"알 수 없는 단계: {stage}")
    if not confirmed.strip():
        raise ValueError("낭독 대본에는 컨펌 원고가 필요하다")
    if stage == "humanize" and not (draft and draft.strip()):
        raise ValueError("humanize 단계에는 낭독 초안이 필요하다")

    headings = manuscript_headings(confirmed)
    if not headings:
        raise ValueError("컨펌 원고에서 섹션 제목을 찾지 못했다")

    narration = load_narration()
    channel = load_channel()
    examples = load_examples(NARRATION_EXAMPLES_DIR)
    warnings = _warn(confirmed, required_sections(load_structure()), "컨펌 원고")
    lang = resolve_lang(None, brief)

    draft_text = draft.strip() if draft else None
    final_text = None

    if stage in {"all", "draft"}:
        messages = narrate_messages(
            narration=narration,
            channel=channel,
            examples=[(path.name, text) for path, text in examples],
            confirmed=confirmed,
            brief=brief,
            lang=lang,
        )
        draft_text = complete(messages, temperature=NARRATE_TEMPERATURE)
        warnings.extend(_warn(draft_text, headings, "낭독 초안"))

    if stage in {"all", "humanize"}:
        if not draft_text:
            raise ValueError("humanize 단계에는 낭독 초안이 필요하다")
        messages = humanize_messages(
            guide=load_humanize_guide(),
            draft=draft_text,
            kind="narration",
            lang=lang,
        )
        final_text = complete(messages, temperature=HUMANIZE_TEMPERATURE)
        warnings.extend(_warn(final_text, headings, "낭독 대본"))

    destination = _write_narration(
        confirmed=confirmed,
        brief=brief,
        draft=draft_text,
        final=final_text,
        examples=examples,
        confirmed_path=confirmed_path,
        output_root=output_root or (ROOT / "output"),
        stage=stage,
    )
    return RunResult(
        output_dir=destination,
        draft_path=destination / "narration-draft.md" if draft_text else None,
        final_path=destination / "narration.md" if final_text else None,
        warnings=warnings,
    )


def _new_output_dir(output_root: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = output_root / stamp
    suffix = 2
    while destination.exists():
        destination = output_root / f"{stamp}-{suffix}"
        suffix += 1
    destination.mkdir(parents=True)
    return destination


def _write_run(
    *,
    brief: str,
    draft: str | None,
    final: str | None,
    examples: list[tuple[Path, str]],
    output_root: Path,
    stage: str,
) -> Path:
    destination = _new_output_dir(output_root)
    (destination / "brief.md").write_text(brief.strip() + "\n", encoding="utf-8")
    if draft:
        (destination / "draft.md").write_text(draft.strip() + "\n", encoding="utf-8")
    if final:
        (destination / "final.md").write_text(final.strip() + "\n", encoding="utf-8")
    manifest = {
        "stage": stage,
        "structure": file_record(STRUCTURE_PATH),
        "channel": file_record(CHANNEL_PATH),
        "humanize_rule": file_record(HUMANIZE_RULE_PATH),
        "examples": [file_record(path) for path, _text in examples],
    }
    (destination / "sources.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def _write_narration(
    *,
    confirmed: str,
    brief: str,
    draft: str | None,
    final: str | None,
    examples: list[tuple[Path, str]],
    confirmed_path: Path | None,
    output_root: Path,
    stage: str,
) -> Path:
    destination = _new_output_dir(output_root)
    confirmed_copy = destination / "confirmed.md"
    confirmed_copy.write_text(confirmed.strip() + "\n", encoding="utf-8")
    (destination / "brief.md").write_text(brief.strip() + "\n", encoding="utf-8")
    if draft:
        (destination / "narration-draft.md").write_text(draft.strip() + "\n", encoding="utf-8")
    if final:
        (destination / "narration.md").write_text(final.strip() + "\n", encoding="utf-8")
    if confirmed_path and confirmed_path.is_file():
        confirmed_record = file_record(confirmed_path)
    else:
        confirmed_record = file_record(confirmed_copy)
    manifest = {
        "stage": f"narrate:{stage}",
        "narration": file_record(NARRATION_PATH),
        "structure": file_record(STRUCTURE_PATH),
        "channel": file_record(CHANNEL_PATH),
        "humanize_rule": file_record(HUMANIZE_RULE_PATH),
        "confirmed": confirmed_record,
        "examples": [file_record(path) for path, _text in examples],
    }
    (destination / "sources.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination
