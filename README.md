# 유튜브 스크립트 파이프라인

주제 브리프를 받아 2차 컨펌용 원고를 만들고, 사람이 그 원고를 컨펌하면 낭독용 완성 대본으로 푼다. 두 단계 모두 나온 글을 `.cursor/rules/avoid-ai-writing.mdc`로 다듬는다.

컨펌 원고의 구조는 `docs/script-structure.md`, 낭독 대본의 분량과 말하는 순서는 `docs/narration.md`에 있다. 코드를 고치지 말고 해당 문서를 고친다.

## 준비

```bash
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

`.env`에 키와 모델을 넣는다. 채팅 완성 API가 OpenAI와 같으면 주소만 해당 서비스로 바꾼다.

```text
YTPIPE_API_KEY=
YTPIPE_BASE_URL=https://api.openai.com/v1
YTPIPE_MODEL=gpt-4o
```

## 실행

```bash
ytpipe check
ytpipe run --brief briefs/example.md --lang en # example.md 파일을 작성해 기본적 틀을 잡아주어야함
ytpipe run --topic "How FAA Opspec A134 is changing pilot hiring forever" --minutes 9 --lang en # 주제만 가지고 draft 만들고 싶은 경우 
ytpipe run --stage humanize --draft output/실행시각/draft.md --lang en
ytpipe narrate --confirmed output/실행시각/final.md --lang en
ytpipe footage --script output/실행시각/narration.md
```

`--lang ko`는 한국어, `--lang en`은 영어다. 생략하면 브리프의 `언어`를 쓰고, 그것도 없으면 한국어다. 섹션 제목은 구조 문서 그대로 두고, 제목 후보와 대사만 그 언어로 쓴다.

`check`는 모델 호출 없이, 구조 문서와 낭독 문서, 다듬기 규칙이 읽히는지 확인한다.

`run` 결과는 `output/실행시각/`에 저장된다.

- `brief.md`: 그 실행에 넣은 브리프
- `draft.md`: 컨펌용 초안
- `final.md`: 다듬기 규칙을 적용한 컨펌용 원고
- `sources.json`: 실행에 사용한 문서의 해시

`final.md`를 사람이 고친 뒤 `narrate`에 넘긴다. 같은 폴더에 `brief.md`가 있으면 그 브리프를 같이 읽는다. 원고와 브리프가 다르면 컨펌 원고를 따른다.

`narrate` 결과는 새 `output/실행시각/`에 저장된다.

- `confirmed.md`: 넘긴 컨펌 원고
- `narration-draft.md`: 낭독 초안
- `narration.md`: 다듬기 규칙을 적용한 낭독 대본

컨펌 원고의 섹션이 대본에서 빠지거나 순서가 바뀌면 파일을 지우지 않고, 터미널에 `확인 필요`로 알린다.

`footage`는 대본의 각 구간에 맞는 Pexels 영상을 받아 `output/실행시각/footage/`에 저장한다. `.env`의 `PEXELS_API_KEY`가 필요하다. 같은 폴더의 `brief.md`가 있으면 검색어를 고를 때 함께 본다. 받은 파일과 출처는 `footage.md`에 적힌다.

## 구조를 학습시키는 방법

1. 컨펌 원고의 섹션과 항목은 `docs/script-structure.md`에서 고친다. `필수 섹션` 목록의 제목이 검증 기준이다.
2. 낭독 대본의 분량과 말하는 순서는 `docs/narration.md`에서 고친다.
3. 말투를 고정하려면 `docs/channel.md`에서 값이 있는 항목만 채운다. 빈 항목은 없는 설정으로 둔다.
4. 컨펌 원고의 참고는 `docs/examples/`, 낭독 대본의 참고는 `docs/narration-examples/`에 `.md`로 넣는다. 각 단계는 최대 두 개, 각 6,000자까지 읽고, 말의 호흡만 참고한다.

다듬기 단계는 섹션과 사실을 유지한 채 `avoid-ai-writing` 규칙으로 문장만 고친다. 컨펌 원고는 3줄 요약을 유지하고, 낭독 대본만 소리 내어 읽는 대사로 다듬는다. 그 규칙 파일은 생성본이므로 직접 수정하지 않는다.
