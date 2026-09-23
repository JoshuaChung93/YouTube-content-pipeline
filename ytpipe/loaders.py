from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRUCTURE_PATH = ROOT / "docs" / "script-structure.md"
CHANNEL_PATH = ROOT / "docs" / "channel.md"
EXAMPLES_DIR = ROOT / "docs" / "examples"
NARRATION_PATH = ROOT / "docs" / "narration.md"
NARRATION_EXAMPLES_DIR = ROOT / "docs" / "narration-examples"
HUMANIZE_RULE_PATH = ROOT / ".cursor" / "rules" / "avoid-ai-writing.mdc"

MAX_EXAMPLES = 2
MAX_EXAMPLE_CHARS = 6000


class SourceError(Exception):
    pass


def read_text(path: Path) -> str:
    if not path.is_file():
        raise SourceError(f"필요한 파일이 없다: {path}")
    return path.read_text(encoding="utf-8")


def strip_frontmatter(text: str) -> str:
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4 :]
    text = text.lstrip()
    text = re.sub(r"^(?:<!--.*?-->\s*)+", "", text, count=1, flags=re.S)
    return text.strip()


def extract_section(text: str, title: str) -> str:
    lines = text.splitlines()
    start = None
    level = None
    for index, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match and match.group(2) == title:
            start = index + 1
            level = len(match.group(1))
            break
    if start is None or level is None:
        raise SourceError(f"구조 문서에 '{title}' 절이 없다")
    body: list[str] = []
    for line in lines[start:]:
        match = re.match(r"^(#{1,6})\s+", line)
        if match and len(match.group(1)) <= level:
            break
        body.append(line)
    return "\n".join(body).strip()


def required_sections(structure: str) -> list[str]:
    body = extract_section(structure, "필수 섹션")
    sections: list[str] = []
    for line in body.splitlines():
        match = re.search(r"`(#{1,6}\s+[^`]+)`", line.strip())
        if match:
            sections.append(match.group(1).strip())
    if not sections:
        raise SourceError("필수 섹션 목록이 비어 있다")
    return sections


def structure_problems(script: str, sections: list[str]) -> list[str]:
    problems: list[str] = []
    last = -1
    for section in sections:
        index = script.find(section)
        if index < 0:
            problems.append(f"없는 섹션: {section}")
        elif index < last:
            problems.append(f"순서가 앞섬: {section}")
        else:
            last = index
    return problems


def load_structure() -> str:
    return read_text(STRUCTURE_PATH).strip()


def load_channel() -> str:
    return read_text(CHANNEL_PATH).strip()


def manuscript_headings(text: str) -> list[str]:
    headings: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"^(#{2,3})\s+(\S.*?)\s*$", line)
        if match:
            headings.append(f"{match.group(1)} {match.group(2)}")
    return headings


def load_narration() -> str:
    return read_text(NARRATION_PATH).strip()


def load_examples(directory: Path | None = None) -> list[tuple[Path, str]]:
    folder = directory or EXAMPLES_DIR
    if not folder.is_dir():
        return []
    picked: list[tuple[Path, str]] = []
    for path in sorted(folder.glob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        if len(text) > MAX_EXAMPLE_CHARS:
            text = text[:MAX_EXAMPLE_CHARS].rstrip() + "\n\n[이하 생략]"
        picked.append((path, text))
        if len(picked) >= MAX_EXAMPLES:
            break
    return picked


def load_humanize_guide() -> str:
    guide = strip_frontmatter(read_text(HUMANIZE_RULE_PATH))
    if "Editing contract" not in guide:
        raise SourceError("다듬기 규칙에서 편집 기준을 찾지 못했다")
    return guide


def file_record(path: Path) -> dict[str, str | int]:
    data = path.read_bytes()
    try:
        display = str(path.relative_to(ROOT))
    except ValueError:
        display = str(path)
    return {
        "path": display,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }
