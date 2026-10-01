# 🏥 KY CAM-ICU/RASS
### AI 보조 기반 디지털 섬망 평가 및 환자 모니터링 시스템

![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.x-000000?logo=flask&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-Database-003B57?logo=sqlite&logoColor=white)
![Google Colab](https://img.shields.io/badge/Google-Colab-F9AB00?logo=googlecolab&logoColor=white)
![Version](https://img.shields.io/badge/Version-v5-blue)

> **본 프로젝트는 교육 및 시연을 목적으로 개발한 시스템이며, 실제 임상 판단이나 의료진의 진단을 대체하지 않습니다.**

---

## 📌 1. 프로젝트 소개

KY CAM-ICU/RASS는 중환자실 환자의 의식 및 진정 수준과 섬망 상태를 체계적으로 평가하고, 평가 결과를 디지털로 기록·관리하는 웹 기반 시스템입니다.

의료진의 RASS 평가를 AI가 참고용으로 보조하고, 간호사가 확정한 RASS 점수와 CAM-ICU 평가 결과를 바탕으로 서버에서 섬망 판정 결과를 자동 계산합니다.

환자별 평가 기록, RASS 변화 추이, 재평가 일정과 병동별 통계를 하나의 시스템에서 확인할 수 있습니다.

### 주요 목표

- RASS 및 CAM-ICU 평가의 디지털화
- AI를 활용한 참고용 RASS 점수 제안
- 의료진의 최종 평가 권한 보장
- CAM-ICU 판정 공식의 일관된 적용
- 환자별 평가 기록 및 상태 변화 모니터링
- 사용자 권한에 따른 환자 정보 접근 관리

---

## 🧠 2. 핵심 평가 도구

### RASS (Richmond Agitation-Sedation Scale)

환자의 각성 및 진정 수준을 -5점부터 +4점까지 평가하는 도구입니다.

| 점수 | 상태 |
|---|---|
| +4 | 폭력적 |
| +3 | 매우 흥분 |
| +2 | 흥분 |
| +1 | 불안 |
| 0 | 깨어 있고 차분함 |
| -1 | 졸림 |
| -2 | 가벼운 진정 |
| -3 | 중등도 진정 |
| -4 | 깊은 진정 |
| -5 | 각성 불가 |

### CAM-ICU (Confusion Assessment Method for the ICU)

중환자실 환자의 섬망을 평가하는 도구로, 다음 네 가지 특징을 확인합니다.

| 항목 | 평가 내용 |
|---|---|
| F1 | 급성 정신 상태 변화 또는 변동 경과 |
| F2 | 주의력 장애 |
| F3 | 의식 수준 변화 |
| F4 | 비체계적 사고 |

**CAM-ICU 양성 판정 공식**

```text
POSITIVE = F1 AND F2 AND (F3 OR F4)
```

판정 공식은 서버에서 계산하며, 사용자가 결과를 직접 지정할 수 없습니다.

---

## ⚙️ 3. 주요 기능

### 🔐 사용자 인증 및 권한 관리

- 간호사 및 관리자 통합 로그인
- Flask Session 기반 사용자 인증
- Werkzeug를 이용한 비밀번호 해싱
- 로그인 시각 자동 기록
- 사용자 권한에 따른 페이지 이동
- 미담당 환자 접근 시 HTTP 403 차단

### 👩‍⚕️ 관리자 페이지

관리자는 간호사 계정과 환자 정보를 관리할 수 있습니다.

**간호사 관리**
- 간호사 등록 및 목록 조회
- 사번, 병동, 담당 환자 수 확인
- 이중 확인을 통한 계정 삭제
- 계정 삭제 시 담당 환자 배정 해제

**환자 관리**
- 환자 등록, 수정 및 삭제
- 환자 이름, 코드, 병실 통합 검색
- 담당 간호사 배정
- 환자 상태 및 진정제·진통제 사용 여부 관리
- 50명 단위 페이지네이션

### 📋 담당 환자 대시보드

간호사는 로그인 후 자신이 담당하는 환자 목록을 확인할 수 있습니다.

**5가지 정렬 기능**
1. 병실 순
2. 위험 순
3. 재평가 필요 순
4. 이름 순
5. 최근 검사 순

환자 이름과 병실을 이용한 실시간 검색을 지원합니다.

**재평가 카운트다운**

| 최근 평가 결과 | 시스템의 재평가 안내 |
|---|---|
| POSITIVE | 4시간 이내 |
| NEGATIVE | 8시간 |
| UNASSESSABLE | RASS 회복 등 상태 변화 시 |
| 미평가 | 첫 평가 필요 |

카운트다운은 30초마다 갱신되며, 재평가 시간이 임박하면 시각적으로 표시합니다.

※ 재평가 간격은 시연용 설정이며 실제 적용 시 의료기관의 프로토콜을 따라야 합니다.

### 📝 6단계 디지털 평가

**STEP 1. 표준 절차 관찰**

간호사가 환자의 반응을 관찰하고 10개의 표준 관찰 항목 중 하나를 선택합니다.

**STEP 2. CAM-ICU 특징 평가**

F1~F4를 평가합니다. RASS -4 이하에서는 해당 평가를 진행하지 않습니다.

**STEP 3. AI 참고 RASS 확인**

선택한 관찰 결과를 기반으로 AI가 참고용 RASS 점수를 제안합니다.

**STEP 4. 간호사 최종 RASS 확정**

간호사가 -5부터 +4까지의 점수 중 최종 RASS를 직접 선택합니다. AI 제안 점수는 자동 확정되지 않습니다.

**STEP 5. 메모 작성**

진정제 용량 변경이나 특이 관찰 사항 등을 선택적으로 기록합니다.

**STEP 6. 평가 저장**

서버에서 CAM-ICU 결과를 계산하고 평가 기록을 저장합니다.

### 🚦 RASS 게이트

```text
최종 RASS >= -3
    → CAM-ICU 평가 진행
    → 서버에서 POSITIVE / NEGATIVE 계산

최종 RASS = -4 또는 -5
    → CAM-ICU 평가 불가
    → UNASSESSABLE
```

### 📈 환자 상세 화면

- 환자 기본 정보 및 입원 상태 확인
- Chart.js 기반 RASS 변화 추이 그래프
- CAM-ICU 결과별 그래프 색상 구분
- 평가 기록 최신순 조회
- 이전 평가 결과 및 메모 확인
- 새로운 평가 바로가기

### 👤 마이페이지

- 간호사 프로필 확인
- 전체 평가 건수 및 결과별 통계
- 담당 환자 목록 조회
- 환자 상태 변경 및 자동 저장
- 환자 상세 화면 이동

### 📊 통계 페이지

전체 환자와 평가 데이터를 분석하고 시각화합니다.

**주요 통계**
- 전체 환자 및 평가 건수
- CAM-ICU 양성률
- 최근 7일 평가 현황
- 병동별 환자 및 평가 현황

**4가지 시각화**
1. CAM-ICU 결과 분포
2. RASS 점수 분포
3. 최근 12주 섬망 발생 추이
4. 병동별 환자 및 평가 건수 비교

병동별 상세 통계와 CAM-ICU 양성 횟수가 많은 환자 10명의 목록도 제공합니다.

---

## 🗃️ 4. 데이터 및 기록 관리

교육·시연을 위한 가상 데이터를 사용합니다.

| 구분 | 내용 |
|---|---|
| 가상 환자 | 10,000명 |
| 가상 평가 기록 | 약 10,000건 |
| 데이터 기간 | 최근 6개월 |
| 데이터베이스 | SQLite |
| 영구 보존 | Google Drive 연동 |

환자별 평가 기록에는 관찰 결과, AI 제안 RASS, 최종 RASS, F1~F4, CAM-ICU 결과, 메모 및 평가 시각이 포함됩니다.

로그인, 평가 저장, 환자 상태 변경, 사용자 및 환자 등록·삭제 등 주요 행동은 감사 로그에 기록합니다.

---

## 🛠️ 5. 기술 스택

| 구분 | 기술 |
|---|---|
| Language | Python 3.13 |
| Backend | Flask 3.x |
| Database | SQLite |
| Authentication | Flask Session |
| Password Security | Werkzeug |
| Visualization | Chart.js 4.4.1 |
| Execution | Google Colab |
| Data Persistence | Google Drive |

---

## 🚀 6. 실행 방법

Google Colab을 이용한 실행을 지원합니다.

### 1. 프로젝트 준비

Google Drive에 프로젝트 압축 파일을 업로드합니다.

```text
cam_icu_rass_v5.zip
```

### 2. Google Drive 연결 및 압축 해제

Colab에서 Google Drive를 마운트한 후 아래 코드를 실행합니다.

```python
import zipfile
import shutil

shutil.rmtree(
    '/content/cam_icu_rass_v5',
    ignore_errors=True
)

with zipfile.ZipFile(
    '/content/drive/MyDrive/cam_icu_rass_v5.zip'
) as z:
    z.extractall('/content/')

print("완료")
```

### 3. 서버 실행

```python
%run /content/cam_icu_rass_v5/colab_start.py
```

실행 후 출력되는 Cloudflare 임시 접속 링크로 웹 시스템에 접속합니다.

**주의사항**

- 최초 실행 시 가상 환자 데이터가 생성됩니다.
- Google Drive 연동 시 데이터가 영구 보존됩니다.
- Colab 세션이 종료되면 임시 접속 링크가 만료됩니다.
- 이전 버전과 새로운 버전을 동시에 실행하지 않도록 주의해야 합니다.

---

## 🔒 7. 보안 및 접근 제어

- 사용자 세션 기반 인증
- 비밀번호 해싱 및 검증
- 역할에 따른 페이지 접근 제어
- 담당 환자 외 접근 차단
- 주요 작업 감사 로그 기록
- CAM-ICU 판정의 서버 측 처리

---

## ⚠️ 8. 사용 범위 및 주의사항

본 시스템은 대학 교육 및 프로젝트 시연을 목적으로 개발되었습니다.

- 실제 환자 정보가 아닌 가상 데이터를 사용합니다.
- AI의 RASS 제안은 참고용입니다.
- 최종 RASS 점수는 의료진이 직접 확정합니다.
- CAM-ICU 결과는 입력된 평가 항목에 따라 서버에서 계산됩니다.
- 실제 임상 환경에서의 사용을 위한 안전성 및 유효성 검증을 완료한 의료기기가 아닙니다.

---

## 📄 9. 프로젝트 버전

**KY CAM-ICU/RASS v5**

디지털 섬망 평가, AI 보조 RASS 제안, 환자 상태 모니터링, 관리자 기능 및 통계 시각화를 포함한 교육·시연용 웹 시스템입니다.
