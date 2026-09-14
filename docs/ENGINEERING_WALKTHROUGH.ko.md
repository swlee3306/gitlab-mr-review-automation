# 5분 코드 리뷰: 리뷰 자동화의 실패 상황 다루기

## 해결하려는 문제

자동 리뷰는 모델을 호출하는 것만으로 끝나지 않습니다. 같은 이벤트가 다시 들어오거나,
리뷰 도중 커밋이 바뀌거나, 중단된 작업이 재시작되면 결과의 중복과 유효성을 관리해야 합니다.
이 공개 구현은 그 주변 제어 로직을 작은 상태 머신과 교체 가능한 어댑터로 구성합니다.

실제 운영 절감 시간·사용자 수·리뷰 정확도를 측정한 자료는 없습니다.
아래는 합성 데이터와 로컬 테스트로 확인할 수 있는 구현 설명입니다.

## 먼저 실행하기

저장소 루트에서 Python 3.11 이상으로 실행합니다. 외부 계정이나 패키지 설치는 필요 없습니다.

```sh
python3 -m reviewflow demo
python3 -m unittest discover -s tests -v
```

2026-09-14 실행에서 첫 이벤트는 `completed`, 같은 이벤트의 두 번째 처리는 `duplicate`였으며,
두 결과의 `attempts`는 모두 1이었습니다. 31개 테스트가 통과했습니다.
데모의 reviewer는 결정적 테스트 대역입니다. 이 결과는 LLM의 판단 품질을 평가하지 않습니다.

## 설계 선택을 코드와 함께 읽기

| 상황 | 구현에서 확인할 선택 | 검증 위치 |
| --- | --- | --- |
| 중복 전달·프로세스 재시작 | SQLite에 처리 상태를 남겨 메모리 수명과 분리 | `test_duplicate_is_not_reviewed_twice`, `test_duplicate_survives_reopening` |
| 리뷰 도중 커밋 변경 | 리뷰 전후 head SHA를 확인 | `test_stale_before_review`, `test_stale_after_review` |
| 동시에 들어온 작업 | 두 연결의 claim 경쟁을 검사 | `test_two_connections_claim_only_once` |
| 만료된 작업자가 늦게 완료 | 재할당된 작업을 이전 작업자가 완료하지 못하도록 제한 | `test_expired_worker_cannot_finish_reclaimed_work` |
| 변경하지 않은 줄에 의견 생성 | 입력 변경 라인에 해당하는 finding만 허용 | `test_outside_changed_lines_rejected` |
| 입력·출력의 민감한 값 | 선택한 패턴을 차단하고 예외 메시지를 숨김 | `test_secret_input_never_reaches_reviewer`, `test_secret_in_reviewer_output_rejected` |

위 테스트는 [tests/test_core.py](../tests/test_core.py)에 있습니다.
그다음 [reviewflow/core.py](../reviewflow/core.py)의 `Store`와 `run_once`를 읽으면
상태 저장과 리뷰 실행 경계가 연결됩니다.

## 의도적으로 남긴 제약

- SQLite 기반 로컬 처리입니다. 대규모 분산 큐의 처리량이나 외부 시스템의 exactly-once를 보장하지 않습니다.
- 재시도 스케줄링과 reviewer 실행 시간 제한은 호출자의 책임입니다.
- [GitLab 읽기 어댑터](../reviewflow/gitlab.py)는 GET 요청을 사용하지만, 댓글 게시·Slack·LLM 연동은 포함하지 않습니다.
- 민감값 검사는 제한된 패턴 검사입니다. 포괄적인 비밀정보 탐지기라고 주장하지 않습니다.
- 테스트 통과는 운영 GitLab에 대한 연결·권한 검증과 다릅니다. 이번 실행에서는 운영 서비스를 호출하지 않았습니다.

## 면접에서 설명할 핵심

“리뷰 자동화의 중복 전달과 커밋 변경 문제를 SQLite 상태 저장 및 SHA 전후 확인으로 다루고,
재할당된 작업에 대한 이전 작업자의 완료를 차단하는 경계를 테스트로 검증했습니다.”

이는 이 공개 저장소의 구현 설명입니다. 회사 전사 도입 실적, 타인 프로젝트 기여,
운영 성능 개선 수치를 대신하는 문구로 사용하지 않습니다.
