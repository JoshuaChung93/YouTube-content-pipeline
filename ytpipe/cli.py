from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ytpipe.loaders import (
    CHANNEL_PATH,
    EXAMPLES_DIR,
    HUMANIZE_RULE_PATH,
    NARRATION_EXAMPLES_DIR,
    NARRATION_PATH,
    ROOT,
    STRUCTURE_PATH,
    load_channel,
    load_examples,
    load_humanize_guide,
    load_narration,
    load_structure,
    required_sections,
)
from ytpipe.language import apply_language, language_name, resolve_lang
from ytpipe.pipeline import build_brief, narrate, run


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            os.environ.setdefault(key, value)


def _read_brief(args: argparse.Namespace) -> str:
    if args.brief:
        path = Path(args.brief)
        if not path.is_file():
            raise SystemExit(f"브리프 파일이 없다: {path}")
        return path.read_text(encoding="utf-8")
    if args.topic:
        return build_brief(
            topic=args.topic,
            audience=args.audience,
            minutes=args.minutes,
            angle=args.angle,
            must_include=args.must_include,
            must_avoid=args.must_avoid,
            cta=args.cta,
        )
    if args.stage == "humanize":
        return "# 브리프\n\n기존 초안만 다듬는 실행이라 브리프가 없다.\n"
    raise SystemExit("브리프 파일(--brief) 또는 주제(--topic)가 필요하다")


def _cmd_check(_args: argparse.Namespace) -> int:
    structure = load_structure()
    sections = required_sections(structure)
    guide = load_humanize_guide()
    channel = load_channel()
    examples = load_examples()
    print(f"구조 문서: {STRUCTURE_PATH} ({len(structure)}자)")
    print("필수 섹션: " + ", ".join(sections))
    print(f"채널 말투: {CHANNEL_PATH} ({len(channel)}자)")
    print(f"참고 스크립트: {len(examples)}개 ({EXAMPLES_DIR})")
    narration = load_narration()
    narration_examples = load_examples(NARRATION_EXAMPLES_DIR)
    print(f"낭독 문서: {NARRATION_PATH} ({len(narration)}자)")
    print(f"참고 대본: {len(narration_examples)}개 ({NARRATION_EXAMPLES_DIR})")
    print(f"다듬기 규칙: {HUMANIZE_RULE_PATH} ({len(guide)}자)")
    return 0


def _with_language(args: argparse.Namespace, brief: str) -> tuple[str, str]:
    try:
        lang = resolve_lang(getattr(args, "lang", None), brief)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(f"언어: {language_name(lang)}")
    return apply_language(brief, lang), lang


def _cmd_run(args: argparse.Namespace) -> int:
    brief, lang = _with_language(args, _read_brief(args))
    draft = None
    if args.draft:
        path = Path(args.draft)
        if not path.is_file():
            raise SystemExit(f"초안 파일이 없다: {path}")
        draft = path.read_text(encoding="utf-8")
    if args.stage == "humanize" and draft is None:
        raise SystemExit("humanize 단계에는 --draft 가 필요하다")
    result = run(brief=brief, stage=args.stage, draft=draft)
    print(f"저장: {result.output_dir}")
    if result.draft_path:
        print(f"초안: {result.draft_path}")
    if result.final_path:
        print(f"최종: {result.final_path}")
    for warning in result.warnings:
        print(f"확인 필요: {warning}", file=sys.stderr)
    if args.stage == "draft" and result.draft_path:
        print(f"컨펌 후: ytpipe narrate --confirmed {result.draft_path} --lang {lang}")
    elif result.final_path:
        print(f"컨펌 후: ytpipe narrate --confirmed {result.final_path} --lang {lang}")
    return 0


def _read_existing(path_text: str, label: str) -> tuple[Path, str]:
    path = Path(path_text)
    if not path.is_file():
        raise SystemExit(f"{label} 파일이 없다: {path}")
    return path, path.read_text(encoding="utf-8")


def _brief_for_narration(args: argparse.Namespace, confirmed_path: Path) -> str:
    if args.brief:
        path, text = _read_existing(args.brief, "브리프")
        print(f"브리프: {path}")
        return text
    sibling = confirmed_path.parent / "brief.md"
    if sibling.is_file() and sibling.resolve() != confirmed_path.resolve():
        print(f"브리프: {sibling}")
        return sibling.read_text(encoding="utf-8")
    return "# 브리프\n\n지정하지 않음. 컨펌 원고에 있는 내용만 사용한다.\n"


def _cmd_narrate(args: argparse.Namespace) -> int:
    confirmed_path, confirmed = _read_existing(args.confirmed, "컨펌 원고")
    brief, _lang = _with_language(args, _brief_for_narration(args, confirmed_path))
    draft = None
    if args.draft:
        _draft_path, draft = _read_existing(args.draft, "낭독 초안")
    if args.stage == "humanize" and draft is None:
        raise SystemExit("humanize 단계에는 --draft 가 필요하다")
    result = narrate(
        confirmed=confirmed,
        brief=brief,
        stage=args.stage,
        draft=draft,
        confirmed_path=confirmed_path,
    )
    print(f"저장: {result.output_dir}")
    if result.draft_path:
        print(f"낭독 초안: {result.draft_path}")
    if result.final_path:
        print(f"낭독 대본: {result.final_path}")
    for warning in result.warnings:
        print(f"확인 필요: {warning}", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ytpipe",
        description="컨펌용 원고를 만들고, 컨펌이 끝나면 낭독용 대본으로 푼다.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="구조 문서와 다듬기 규칙이 읽히는지 확인한다")
    check.set_defaults(func=_cmd_check)

    run_parser = sub.add_parser("run", help="브리프로 컨펌 원고를 만든다")
    run_parser.add_argument("--brief", help="브리프 마크다운 경로")
    run_parser.add_argument("--topic", help="주제. --brief 가 없을 때 쓴다")
    run_parser.add_argument("--audience", help="시청자")
    run_parser.add_argument("--minutes", type=int, help="목표 길이(분)")
    run_parser.add_argument("--angle", help="각도")
    run_parser.add_argument("--must-include", help="꼭 넣을 내용")
    run_parser.add_argument("--must-avoid", help="넣지 말 것")
    run_parser.add_argument("--cta", help="마무리 행동")
    run_parser.add_argument(
        "--stage",
        choices=["all", "draft", "humanize"],
        default="all",
        help="all은 초안 뒤 다듬기, draft는 초안만, humanize는 있는 초안만 다듬기",
    )
    run_parser.add_argument("--draft", help="humanize 단계에 넣을 초안 경로")
    run_parser.add_argument(
        "--lang",
        choices=["ko", "en"],
        help="원고 언어. ko는 한국어, en은 영어. 없으면 브리프의 언어, 그것도 없으면 ko",
    )
    run_parser.set_defaults(func=_cmd_run)

    narrate_parser = sub.add_parser("narrate", help="컨펌된 원고로 낭독 대본을 만든다")
    narrate_parser.add_argument("--confirmed", required=True, help="사람이 컨펌한 원고 경로")
    narrate_parser.add_argument("--brief", help="브리프 경로. 없으면 원고와 같은 폴더의 brief.md를 찾는다")
    narrate_parser.add_argument(
        "--stage",
        choices=["all", "draft", "humanize"],
        default="all",
        help="all은 낭독 초안 뒤 다듬기, draft는 초안만, humanize는 있는 초안만 다듬기",
    )
    narrate_parser.add_argument("--draft", help="humanize 단계에 넣을 낭독 초안 경로")
    narrate_parser.add_argument(
        "--lang",
        choices=["ko", "en"],
        help="대본 언어. ko는 한국어, en은 영어. 없으면 브리프의 언어, 그것도 없으면 ko",
    )
    narrate_parser.set_defaults(func=_cmd_narrate)
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as error:
        name = type(error).__name__
        if name in {"LLMError", "SourceError", "ValueError"}:
            print(str(error), file=sys.stderr)
            return 1
        raise
