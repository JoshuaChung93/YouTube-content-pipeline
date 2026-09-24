import unittest

from ytpipe.footage import best_video, clean_query, file_slug, script_sections


SAMPLE = """
# 제목

## ① 인트로 (시작 후 ~30초)

조종석에서 계기를 본다.

## ② 본론/행동 유도

### ②-A: OpSpec A134 in Context

항공사 면접 장면을 보여 준다.

## ③ 아웃트로

다음 비행을 준비한다.
"""


class FootageTests(unittest.TestCase):
    def test_sections_skip_empty_parent(self) -> None:
        headings = [section.heading for section in script_sections(SAMPLE)]
        self.assertEqual(
            headings,
            [
                "① 인트로 (시작 후 ~30초)",
                "②-A: OpSpec A134 in Context",
                "③ 아웃트로",
            ],
        )

    def test_clean_query_keeps_six_words(self) -> None:
        self.assertEqual(clean_query('"pilot cockpit at night, extra words here"'), "pilot cockpit at night extra words")

    def test_best_video_prefers_short_1080p(self) -> None:
        videos = [
            {
                "duration": 90,
                "video_files": [
                    {"file_type": "video/mp4", "width": 3840, "height": 2160, "link": "http://big"}
                ],
            },
            {
                "duration": 12,
                "video_files": [
                    {"file_type": "video/mp4", "width": 1920, "height": 1080, "link": "http://hd"},
                    {"file_type": "video/mp4", "width": 1080, "height": 1920, "link": "http://tall"},
                ],
            },
        ]
        chosen_video, chosen_file = best_video(videos)
        self.assertEqual(chosen_file["link"], "http://hd")
        self.assertEqual(chosen_video["duration"], 12)

    def test_file_slug(self) -> None:
        self.assertEqual(file_slug(2, "②-A: OpSpec A134 in Context"), "02-opspec-a134-in-context")


if __name__ == "__main__":
    unittest.main()
