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
