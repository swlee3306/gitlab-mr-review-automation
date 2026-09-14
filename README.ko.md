# MR 리뷰 자동화 — 실행 가능한 범용 데모

자동 리뷰에서 중요한 중복 요청, 오래된 커밋, 재시도, 작업 소유권을 작은 코드와 테스트로 검증하는 프로젝트입니다.
실제 GitLab·LLM·Slack 계정 없이 Python 3.11 이상에서 실행합니다.

```sh
git clone https://github.com/swlee3306/gitlab-mr-review-automation.git
cd gitlab-mr-review-automation
python3 -m reviewflow demo
python3 -m unittest discover -s tests -v
```

같은 합성 이벤트를 두 번 처리하면 첫 결과는 `completed`, 두 번째는 `duplicate`입니다.
결정적 가짜 reviewer를 사용하므로 AI 추론 결과라고 주장하지 않습니다.

주요 검증 대상은 SQLite 지속성, 커밋 SHA 전후 확인, 변경 라인에만 finding 허용,
일시 오류의 최대 3회 시도, 만료 후 재할당된 작업에 대한 이전 worker의 완료 차단입니다.
원문 소스나 reviewer 예외 메시지는 상태 DB에 저장하지 않습니다.

`gitlab` 명령은 HTTPS GitLab API에서 MR 변경분을 읽어 로컬에서 검사합니다.
페이지 나눔·변경 라인·SHA 일치 여부를 검증하고, 댓글 게시나 배포는 하지 않습니다.
실제 연동은 환경변수 `GITLAB_TOKEN`을 사용하며, `demo`와 테스트에는 토큰이 필요 없습니다.
webhook 서버·LLM·Slack 연동은 포함하지 않았습니다. `.env.example`은 자동으로 읽지 않습니다.

입력 형식·상태·제약과 확장 계약은 [영문 README](README.md)에 설명했습니다.

## 설계와 검증 사례

[5분 코드 리뷰 가이드](docs/ENGINEERING_WALKTHROUGH.ko.md)에서 중복 처리, 커밋 변경,
만료된 작업자의 결과 차단을 실제 테스트와 연결해 확인할 수 있습니다.
운영 도입 효과나 AI 리뷰 정확도를 주장하는 사례가 아니라 공개 구현의 검증 기록입니다.

## 라이선스

[MIT 라이선스](LICENSE)를 적용합니다. Copyright (c) 2026 swlee3306.
