"""AI RASS 해석 정확도 평가.

사용법:  python eval_ai.py [사례파일.csv]
CSV 열: narrative, expected  (expected가 비어 있으면 '판단 보류'가 정답)
API 키가 설정돼 있어야 한다. 비교용으로 기존 키워드 방식 결과도 함께 출력한다.

⚠️ tests/ai_cases.csv는 형식 예시다. 발표용 평가는 팀원이 직접 쓴 사례로 하세요.
   (AI가 만든 문제로 AI를 채점하면 공정한 평가가 아닙니다.)
"""
import csv
import sys

from ai_rass import suggest_rass_ai
from cam_icu_logic import suggest_rass


def main(path="tests/ai_cases.csv"):
    with open(path, encoding="utf-8") as f:
        cases = list(csv.DictReader(f))
    ai_ok = kw_ok = abstain = errors = 0
    for i, case in enumerate(cases, 1):
        expected = int(case["expected"]) if case["expected"].strip() else None
        ai = suggest_rass_ai(case["narrative"])
        kw = suggest_rass(case["narrative"])["score"]
        if ai["status"] in ("UNAVAILABLE", "ERROR"):
            errors += 1
        if ai["status"] == "ABSTAIN":
            abstain += 1
        ai_ok += ai["score"] == expected
        kw_ok += kw == expected
        mark = "O" if ai["score"] == expected else "X"
        print(f"{i:2d}. [{mark}] 정답 {expected}  AI {ai['score']}  키워드 {kw}  | {case['narrative']}")
        if ai["status"] != "SCORED":
            print(f"      └ {ai['status']}: {ai['reason']}")
    n = len(cases)
    print(f"\nAI 정확도      {ai_ok}/{n} ({ai_ok / n * 100:.1f}%)  · 판단 보류 {abstain}건 · 오류 {errors}건")
    print(f"키워드 정확도  {kw_ok}/{n} ({kw_ok / n * 100:.1f}%)")


if __name__ == "__main__":
    main(*sys.argv[1:])
