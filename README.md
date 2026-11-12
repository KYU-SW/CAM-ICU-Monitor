# CAM-ICU/RASS 디지털 섬망 평가 시스템 v2

교육·시연용 Flask 프로젝트입니다. 실제 임상 진단을 대신하지 않습니다.

## 주요 기능
- 간호사 로그인과 담당 병동 기반 접근 제한
- 환자 목록, 상세 기록, 간호사 마이페이지
- 표준 관찰 기록 기반 시연용 AI RASS 참고 제안
- 간호사가 최종 RASS 확정
- RASS -4/-5 게이트 및 CAM-ICU 서버 계산
- 공식: F1 AND F2 AND (F3 OR F4)
- 감사 로그와 SQLite 저장

## 시연 계정
- `nurse01 / 1234` (중환자실 A, 환자 3명)
- `nurse02 / 1234` (중환자실 B, 환자 2명)

## 로컬 실행
```bash
python -m pip install -r requirements.txt
python app.py
```

## Colab 실행
ZIP을 `/content`에 업로드·압축 해제한 뒤 `colab_start.py`를 실행합니다.
Google Drive에 DB를 보존하려면 먼저 Drive를 연결하고 `CAM_ICU_DB_PATH` 환경변수를 Drive 경로로 지정합니다.

## v11 변경 사항
- **AI 관찰 해석:** 간호사가 쓴 관찰 서술을 LLM이 RASS 공식 정의에 맞춰 해석하고, 제안 점수와 서술 원문 인용을 보여줍니다. 인용이 원문에 없으면 점수를 버립니다(환각 차단). 근거가 부족하면 "판단 보류"로 답합니다. 최종 RASS는 간호사가 확정하며, AI 제안과 다르면 경고가 뜹니다.
- **통계 권한:** 간호사는 소속 병동 집계만 보고, POSITIVE 상위 환자 이름은 담당 환자만 보입니다. 관리자는 전체를 봅니다.
- 이전 "AI 참고 점수"(표에서 점수를 찾던 기능)는 제거했습니다. 2단계 관찰을 고르면 최종 RASS 칸이 자동으로 채워집니다.
- 가상 평가 기록은 AI를 실행한 적이 없으므로 `NOT_RUN`으로 저장됩니다.

## AI 설정
키 하나만 있으면 됩니다.

| 서비스 | 키 이름 | 기본 모델 |
|---|---|---|
| Google Gemini | `GEMINI_API_KEY` | `gemini-2.5-flash` |
| OpenAI | `OPENAI_API_KEY` | `gpt-4.1-mini` |
| Anthropic | `ANTHROPIC_API_KEY` | `claude-haiku-4-5` |

- **Colab:** 왼쪽 🔑(Secrets)에 키 이름과 값을 추가하고 "노트북 액세스"를 켭니다.
- **PythonAnywhere:** WSGI 파일에서 `os.environ["GEMINI_API_KEY"] = "..."`처럼 설정합니다.
- 모델 이름이 바뀌었으면 `AI_MODEL`로 지정합니다. 여러 키가 있으면 `AI_PROVIDER`로 고릅니다.
- **API 키를 코드나 GitHub에 절대 넣지 마세요.**
- 키가 없으면 앱은 정상 동작하고, AI 해석만 "사용 불가"로 표시됩니다.

## AI 정확도 평가
```bash
python eval_ai.py tests/ai_cases.csv
```
`tests/ai_cases.csv`는 형식 예시입니다. 발표용 평가는 팀원이 정답 RASS를 붙여 직접 쓴 사례로 하세요. 기존 키워드 방식과의 정확도 비교도 함께 출력됩니다.
