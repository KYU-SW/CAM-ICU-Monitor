import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ai_rass
from ai_rass import parse_response, suggest_rass_ai

NARRATIVE = "이름 부르니 눈 떴는데 5초쯤 보다가 다시 감음"


class AiRassTest(unittest.TestCase):
    def setUp(self):
        self.saved = {k: os.environ.pop(k, None) for k in
                      ("GEMINI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AI_PROVIDER")}

    def tearDown(self):
        for k, v in self.saved.items():
            if v is not None:
                os.environ[k] = v

    def test_scored_with_quoted_evidence(self):
        r = parse_response('{"score": -2, "criterion": "가벼운 진정", "evidence": "5초쯤 보다가 다시 감음", "missing": ""}', NARRATIVE)
        self.assertEqual((r["status"], r["score"]), ("SCORED", -2))

    def test_hallucinated_evidence_blocked(self):
        r = parse_response('{"score": -2, "criterion": "x", "evidence": "눈맞춤 3초 유지", "missing": ""}', NARRATIVE)
        self.assertEqual((r["status"], r["score"]), ("ABSTAIN", None))

    def test_out_of_range_and_bad_json(self):
        self.assertEqual(parse_response('{"score": 7, "evidence": "눈 떴는데"}', NARRATIVE)["status"], "ERROR")
        self.assertEqual(parse_response('{"score": "-2", "evidence": "눈 떴는데"}', NARRATIVE)["status"], "ERROR")
        self.assertEqual(parse_response("잘 모르겠습니다", NARRATIVE)["status"], "ERROR")

    def test_null_score_abstains(self):
        r = parse_response('{"score": null, "missing": "자극 단계 정보 없음"}', NARRATIVE)
        self.assertEqual(r["status"], "ABSTAIN")
        self.assertIn("자극 단계", r["reason"])

    def test_no_key_unavailable(self):
        self.assertEqual(suggest_rass_ai(NARRATIVE)["status"], "UNAVAILABLE")

    def test_empty_narrative(self):
        self.assertEqual(suggest_rass_ai("  ")["status"], "ABSTAIN")

    def test_with_fake_llm(self):
        os.environ["GEMINI_API_KEY"] = "test"
        fake = lambda provider, prompt: '```json\\n{"score": -2, "criterion": "가벼운 진정", "evidence": "눈 떴는데 5초쯤 보다가", "missing": ""}\\n```'
        r = suggest_rass_ai(NARRATIVE, caller=fake)
        self.assertEqual((r["status"], r["score"]), ("SCORED", -2))

    def test_prompt_contains_criteria_and_text(self):
        prompt = ai_rass.build_prompt(NARRATIVE)
        self.assertIn(NARRATIVE, prompt)
        self.assertIn("-5:", prompt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
