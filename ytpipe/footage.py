from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from ytpipe.llm import LLMError, complete
from ytpipe.loaders import ROOT
from ytpipe.pipeline import _new_output_dir

QUERY_INSTRUCTIONS = """대본 한 구간에 붙일 자료화면의 Pexels 검색어를 만든다.
눈에 찍히는 장면이어야 한다. 영어 2~6단어만 출력한다.
규제 이름, 기관 약어, 추상 개념은 그 장면을 보여 주는 사물이나 장소로 바꾼다.
설명, 따옴표, 번호는 붙이지 않는다."""


class FootageError(Exception):
    pass


@dataclass(frozen=True)
class Section:
    heading: str
    body: str


def script_sections(text: str) -> list[Section]:
    lines = text.splitlines()
    marks: list[tuple[int, str]] = []
    in_fence = False
    for index, line in enumerate(lines):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"^#{2,3}\s+(\S.*?)\s*$", line)
        if match:
            marks.append((index, match.group(1).strip()))
    sections: list[Section] = []
    for position, (start, heading) in enumerate(marks):
        end = marks[position + 1][0] if position + 1 < len(marks) else len(lines)
        body = "\n".join(lines[start + 1 : end]).strip()
        if body:
            sections.append(Section(heading, body))
    return sections


def clean_query(text: str) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""
    line = line.strip().strip('"').strip("'")
    line = re.sub(r"[^\w\s-]", " ", line, flags=re.UNICODE)
    return " ".join(line.split()[:6])


def fallback_query(section: Section) -> str:
    words = re.findall(r"[A-Za-z]{4,}", f"{section.heading} {section.body}")
    stop = {"this", "that", "with", "from", "your", "have", "will", "what", "when", "into"}
    picked = [word for word in words if word.lower() not in stop][:5]
    return " ".join(picked)


def choose_video_file(video: dict) -> dict | None:
    files = [
        item
        for item in video.get("video_files", [])
        if item.get("file_type") == "video/mp4" and item.get("link")
    ]
    landscape = [
        item
        for item in files
        if (item.get("width") or 0) >= (item.get("height") or 1)
    ]
    pool = landscape or files
    if not pool:
        return None
    return max(
        pool,
        key=lambda item: (
            (item.get("width") or 0) >= 1280,
            -abs((item.get("width") or 0) - 1920),
        ),
    )


def best_video(videos: list[dict]) -> tuple[dict, dict] | None:
    ranked: list[tuple[int, int, dict, dict]] = []
    for video in videos:
        chosen = choose_video_file(video)
        if not chosen:
            continue
        duration = video.get("duration") or 0
        usable = 1 if 4 <= duration <= 45 else 0
        width = chosen.get("width") or 0
        ranked.append((usable, -abs(width - 1920), video, chosen))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return ranked[0][2], ranked[0][3]


def file_slug(index: int, heading: str) -> str:
    name = heading.split(":", 1)[-1]
    ascii_name = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not ascii_name:
        ascii_name = "section"
    return f"{index:02d}-{ascii_name[:40].strip('-')}"


def visual_query(section: Section, brief: str) -> str:
    user = "\n".join(["# 브리프", brief.strip(), "", "# 구간", section.heading, "", section.body[:1200]])
    try:
        raw = complete(
            [
                {"role": "system", "content": QUERY_INSTRUCTIONS},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
        )
    except LLMError:
        raw = ""
    query = clean_query(raw) or fallback_query(section)
    if not query:
        raise FootageError(f"검색어를 만들지 못했다: {section.heading}")
    return query


def pexels_key() -> str:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        raise FootageError("자료화면을 받으려면 .env에 PEXELS_API_KEY가 필요하다. https://www.pexels.com/api/")
    return key


def search_pexels(query: str, api_key: str) -> list[dict]:
    url = "https://api.pexels.com/videos/search?" + urllib.parse.urlencode(
        {"query": query, "per_page": 8, "orientation": "landscape"}
    )
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": api_key,
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise FootageError(f"Pexels 검색이 실패했다 ({error.code}): {detail}") from error
    except urllib.error.URLError as error:
        raise FootageError(f"Pexels에 연결하지 못했다: {error.reason}") from error
    videos = payload.get("videos")
    return videos if isinstance(videos, list) else []


def download_file(url: str, dest: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "ytpipe"})
    try:
        with urllib.request.urlopen(request, timeout=180) as response, dest.open("wb") as handle:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
    except urllib.error.URLError as error:
        raise FootageError(f"영상 다운로드가 실패했다: {error}") from error


def _sibling_brief(script_path: Path) -> str:
    sibling = script_path.parent / "brief.md"
    if sibling.is_file() and sibling.resolve() != script_path.resolve():
        return sibling.read_text(encoding="utf-8")
    return ""


def collect_footage(script_path: Path, *, output_root: Path | None = None) -> Path:
    script = script_path.read_text(encoding="utf-8")
    sections = script_sections(script)
    if not sections:
        raise FootageError("대본에서 본문이 있는 구간을 찾지 못했다")
    api_key = pexels_key()
    brief = _sibling_brief(script_path)
    destination = _new_output_dir(output_root or (ROOT / "output"))
    folder = destination / "footage"
    folder.mkdir()
    rows: list[str] = [
        "# 자료화면",
        "",
        f"- 대본: {script_path}",
        "- 출처: Pexels. 파일은 Pexels License로 영상에 쓸 수 있다.",
        "",
    ]
    for index, section in enumerate(sections, start=1):
        query = visual_query(section, brief)
        match = best_video(search_pexels(query, api_key))
        slug = file_slug(index, section.heading)
        rows.extend([f"## {index:02d}. {section.heading}", "", f"- 검색어: {query}"])
        if match is None:
            rows.extend(["- 파일: 없음", ""])
            print(f"없음: {section.heading} ({query})")
            continue
        video, chosen = match
        filename = f"{slug}.mp4"
        download_file(str(chosen["link"]), folder / filename)
        user = video.get("user") if isinstance(video.get("user"), dict) else {}
        rows.extend(
            [
                f"- 파일: footage/{filename}",
                f"- 영상: {video.get('url', '')}",
                f"- 촬영: {user.get('name', '')}",
                f"- 길이: {video.get('duration', '')}초",
                "",
            ]
        )
        print(f"받음: {section.heading} -> {filename}")
    (destination / "footage.md").write_text("\n".join(rows), encoding="utf-8")
    return destination
