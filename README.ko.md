# MR 리뷰 자동화 — 실행 가능한 범용 데모

자동 리뷰에서 중요한 중복 요청, 오래된 커밋, 재시도, 작업 소유권을 작은 코드와 테스트로 검증하는 프로젝트입니다.
실제 GitLab·LLM·Slack 계정 없이 Python 3.11 이상에서 실행합니다.

```sh
python3 -m reviewflow demo
python3 -m unittest discover -s tests -v
```

같은 합성 이벤트를 두 번 처리하면 첫 결과는 `completed`, 두 번째는 `duplicate`입니다.
결정적 가짜 reviewer를 사용하므로 AI 추론 결과라고 주장하지 않습니다.

주요 검증 대상은 SQLite 지속성, 커밋 SHA 전후 확인, 변경 라인에만 finding 허용,
일시 오류의 최대 3회 시도, 만료 후 재할당된 작업에 대한 이전 worker의 완료 차단입니다.
원문 소스나 reviewer 예외 메시지는 상태 DB에 저장하지 않습니다.

실제 webhook 수신·외부 API 연동·메시지 게시 기능은 포함하지 않았습니다.
제공되는 `head`와 `reviewer` adapter 경계에서 확장할 수 있습니다.
`.env.example`은 안내용이며 CLI가 읽지 않습니다. 실제 토큰은 필요하지 않습니다.

입력 형식·상태·제약과 확장 계약은 [영문 README](README.md)에 설명했습니다.
