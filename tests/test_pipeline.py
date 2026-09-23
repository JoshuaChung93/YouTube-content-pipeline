import os
import tempfile
import unittest
from pathlib import Path

from ytpipe.cli import load_dotenv
from ytpipe.loaders import (
    load_humanize_guide,
    load_narration,
    load_structure,
    manuscript_headings,
    required_sections,
    structure_problems,
    strip_frontmatter,
)
from ytpipe.pipeline import build_brief
from ytpipe.prompts import generate_messages, humanize_messages, narrate_messages
from ytpipe.textutil import strip_fences
from ytpipe.llm import locks_temperature, request_body, temperature_was_rejected


class PipelineSourceTests(unittest.TestCase):
    def test_required_sections_come_from_the_structure_doc(self) -> None:
        sections = required_sections(load_structure())
        self.assertEqual(
            sections,
            [
                "## ① 인트로 (시작 후 ~30초)",
                "## ② 본론/행동 유도",
                "### ②-A",
                "## ③ 아웃트로",
            ],
        )

    def test_section_order(self) -> None:
        sections = required_sections(load_structure())
        in_order = "\n".join(sections)
        self.assertEqual(structure_problems(in_order, sections), [])
        swapped = "\n".join(
            [
                "## ① 인트로 (시작 후 ~30초)",
                "### ②-A",
                "## ② 본론/행동 유도",
                "## ③ 아웃트로",
            ]
        )
        problems = structure_problems(swapped, sections)
        self.assertTrue(any("순서" in problem for problem in problems))

    def test_humanize_guide_drops_file_generation_note(self) -> None:
        guide = load_humanize_guide()
        self.assertIn("Editing contract", guide)
        self.assertNotIn("do not edit by hand", guide)
        self.assertGreater(len(guide), 1000)

    def test_frontmatter_and_comment_are_removed(self) -> None:
        raw = (
            "---\n"
            "description: x\n"
            "---\n"
            "<!-- GENERATED FILE — do not edit by hand. -->\n\n"
            "# Title\n"
        )
        self.assertTrue(strip_frontmatter(raw).startswith("# Title"))

    def test_generate_prompt_includes_structure_and_brief(self) -> None:
        messages = generate_messages(
            structure="STRUCTURE_MARK",
            channel="CHANNEL_MARK",
            examples=[],
            brief="BRIEF_MARK",
        )
        self.assertIn("STRUCTURE_MARK", messages[0]["content"])
        self.assertIn("CHANNEL_MARK", messages[0]["content"])
        self.assertEqual(messages[1]["content"], "BRIEF_MARK")

    def test_humanize_prompt_includes_the_guide_and_draft(self) -> None:
        messages = humanize_messages(guide="GUIDE_MARK", draft="DRAFT_MARK")
        self.assertIn("rewrite", messages[0]["content"])
        self.assertIn("GUIDE_MARK", messages[0]["content"])
        self.assertIn("3줄", messages[0]["content"])
        self.assertEqual(messages[1]["content"], "DRAFT_MARK")
        spoken = humanize_messages(guide="GUIDE_MARK", draft="DRAFT_MARK", kind="narration")
        self.assertIn("낭독 대본", spoken[0]["content"])

    def test_narrate_prompt_follows_the_confirmed_manuscript(self) -> None:
        messages = narrate_messages(
            narration="NARRATION_MARK",
            channel="CHANNEL_MARK",
            examples=[],
            confirmed="CONFIRMED_MARK",
            brief="BRIEF_MARK",
        )
        self.assertIn("NARRATION_MARK", messages[0]["content"])
        self.assertIn("컨펌 원고를 따른다", messages[0]["content"])
        self.assertIn("CONFIRMED_MARK", messages[1]["content"])
        self.assertIn("BRIEF_MARK", messages[1]["content"])
        self.assertIn("낭독", load_narration())

    def test_manuscript_headings_keep_confirmed_order(self) -> None:
        confirmed = "\n".join(
            [
                "# 제목",
                "## ① 인트로 (시작 후 ~30초)",
                "```",
                "## 빠진 제목",
                "```",
                "### ②-A: 하루가 성립하는가",
                "## ③ 아웃트로",
            ]
        )
        headings = manuscript_headings(confirmed)
        self.assertEqual(
            headings,
            [
                "## ① 인트로 (시작 후 ~30초)",
                "### ②-A: 하루가 성립하는가",
                "## ③ 아웃트로",
            ],
        )
        self.assertEqual(structure_problems("\n".join(headings), headings), [])

    def test_narrate_rejects_a_manuscript_without_sections(self) -> None:
        from ytpipe.pipeline import narrate

        with self.assertRaises(ValueError):
            narrate(confirmed="# 제목\n본문만 있다.", brief="브리프")

    def test_narrate_reads_a_sibling_brief(self) -> None:
        import argparse

        from ytpipe.cli import _brief_for_narration

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            confirmed = root / "final.md"
            confirmed.write_text("# 원고\n", encoding="utf-8")
            (root / "brief.md").write_text("BRIEF_SIBLING\n", encoding="utf-8")
            text = _brief_for_narration(argparse.Namespace(brief=None), confirmed)
        self.assertIn("BRIEF_SIBLING", text)

    def test_gpt_6_luna_omits_temperature(self) -> None:
        self.assertTrue(locks_temperature("gpt-6-luna"))
        self.assertFalse(locks_temperature("gpt-4o"))
        body = request_body("gpt-6-luna", [{"role": "user", "content": "안녕"}], None)
        self.assertNotIn("temperature", body)
        kept = request_body("gpt-4o", [{"role": "user", "content": "안녕"}], 0.7)
        self.assertEqual(kept["temperature"], 0.7)

    def test_temperature_rejection_matches_the_api_error(self) -> None:
        detail = """{
  "error": {
    "message": "Unsupported value: 'temperature' does not support 0.7 with this model. Only the default (1) value is supported.",
    "type": "invalid_request_error",
    "param": "temperature",
    "code": "unsupported_value"
  }
}"""
        self.assertTrue(temperature_was_rejected(400, detail))
        self.assertFalse(temperature_was_rejected(401, detail))

    def test_strip_fences(self) -> None:
        self.assertEqual(strip_fences("```markdown\n# 제목\n```"), "# 제목")
        self.assertEqual(strip_fences("# 제목"), "# 제목")

    def test_dotenv_does_not_override_existing_values(self) -> None:
        held = "YTPIPE_TEST_HELD"
        fresh = "YTPIPE_TEST_FRESH"
        os.environ[held] = "already"
        os.environ.pop(fresh, None)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(f"{held}=fromfile\n{fresh}=1\n", encoding="utf-8")
            load_dotenv(path)
        self.assertEqual(os.environ[held], "already")
        self.assertEqual(os.environ[fresh], "1")
        del os.environ[held]
        del os.environ[fresh]

    def test_brief_keeps_unspecified_fields_empty(self) -> None:
        brief = build_brief(topic="아침 목록", minutes=8)
        self.assertIn("주제: 아침 목록", brief)
        self.assertIn("목표 길이: 8분", brief)
        self.assertIn("시청자: 지정하지 않음", brief)

    def test_language_flag_overrides_the_brief(self) -> None:
        from ytpipe.language import apply_language, language_in_brief, resolve_lang
        from ytpipe.prompts import generate_messages, narrate_messages

        brief = "# 브리프\n\n- Language: English\n- 주제: hiring\n"
        self.assertEqual(language_in_brief(brief), "en")
        self.assertEqual(resolve_lang("ko", brief), "ko")
        stamped = apply_language(brief, "en")
        self.assertIn("- 언어: 영어", stamped)
        self.assertNotIn("Language:", stamped)

        messages = generate_messages(
            structure="구조",
            channel="말투",
            examples=[],
            brief=stamped,
            lang="en",
        )
        self.assertIn("언어는 영어다", messages[0]["content"])
        spoken = narrate_messages(
            narration="낭독",
            channel="말투",
            examples=[],
            confirmed="원고",
            brief=stamped,
            lang="en",
        )
        self.assertIn("150단어", spoken[0]["content"])
        self.assertEqual(resolve_lang(None, None), "ko")


if __name__ == "__main__":
    unittest.main()
