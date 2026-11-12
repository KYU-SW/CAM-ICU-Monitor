"""LLM 기반 RASS 해석.

간호사가 자유롭게 쓴 관찰 서술을 RASS 공식 정의에 맞춰 해석하고,
제안 점수와 근거(서술 원문 인용)를 돌려준다. 최종 RASS는 간호사가 확정한다.

API 키 설정 (하나만 있으면 됨, 환경변수 또는 Colab Secrets):
    GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY
선택 설정:
    AI_PROVIDER = gemini | openai | anthropic   (생략하면 키가 있는 쪽 사용)
    AI_MODEL    = 모델 이름                      (생략하면 아래 기본값)
"""
import json
import os
import re
import urllib.error
import urllib.request

RASS_CRITERIA = [
    (4, "공격적: 명백히 폭력적이며 의료진에게 즉각적인 위험이 있음"),
    (3, "매우 초조: 튜브나 카테터를 잡아당기거나 제거함, 공격적임"),
    (2, "초조: 목적 없는 움직임이 잦음, 인공호흡기와 맞지 않음(저항)"),
    (1, "안절부절: 불안하거나 걱정스러워하지만 움직임이 공격적이거나 격렬하지 않음"),
    (0, "깨어 있고 차분함"),
    (-1, "졸림: 완전히 깨어 있지는 않지만 목소리에 눈을 뜨고 10초 이상 눈맞춤 유지"),
    (-2, "가벼운 진정: 목소리에 잠깐 깨어나 눈맞춤하지만 10초 미만"),
    (-3, "중등도 진정: 목소리에 움직이거나 눈을 뜨지만 눈맞춤은 없음"),
    (-4, "깊은 진정: 목소리에는 반응 없고 신체 자극에 움직이거나 눈을 뜸"),
    (-5, "깨울 수 없음: 목소리와 신체 자극 모두에 반응 없음"),
]

DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-4.1-mini",
    "anthropic": "claude-haiku-4-5",
}
KEY_NAMES = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}
MAX_NARRATIVE = 600
TIMEOUT_SECONDS = 25


def build_prompt(narrative):
    criteria = "\n".join(f"{score:+d}: {text}" for score, text in RASS_CRITERIA)
    return f"""너는 중환자실 간호사의 RASS(Richmond Agitation-Sedation Scale) 평가를 돕는 보조자다.
아래 [관찰 서술]만 근거로, [RASS 기준] 중 어디에 해당하는지 판단하라.

규칙:
1. 서술에 적힌 사실만 사용한다. 적히지 않은 반응, 자극, 시간은 추측하지 않는다.
2. 점수를 정하려면 자극 단계(무자극/목소리/신체 자극)와 반응이 서술에 있어야 한다.
   깨어 있지 않은 환자에서 눈맞춤 시간이 10초 이상인지 미만인지 알 수 없으면 -1과 -2를 구분하지 않는다.
3. 근거가 부족하면 score를 null로 하고 missing에 부족한 정보를 적는다.
4. evidence에는 판단 근거가 된 [관찰 서술]의 구절을 **한 글자도 바꾸지 말고** 그대로 복사한다.
5. 섬망 여부나 치료는 판단하지 않는다.

[RASS 기준]
{criteria}

[관찰 서술]
{narrative}

다음 JSON 하나만 출력하라. 다른 글은 쓰지 마라.
{{"score": 정수(-5~4) 또는 null, "criterion": "해당 기준 문장", "evidence": "서술 원문 인용", "missing": "부족한 정보 또는 빈 문자열"}}"""


def detect_provider():
    provider = os.environ.get("AI_PROVIDER", "").strip().lower()
    if provider in KEY_NAMES:
        return provider if os.environ.get(KEY_NAMES[provider]) else None
    for name, key in KEY_NAMES.items():
        if os.environ.get(key):
            return name
    return None


def _post(url, payload, headers):
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers}, method="POST")
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def call_llm(provider, prompt):
    """선택한 서비스에 프롬프트를 보내고 응답 텍스트를 돌려준다."""
    key = os.environ[KEY_NAMES[provider]]
    model = os.environ.get("AI_MODEL") or DEFAULT_MODELS[provider]
    if provider == "gemini":
        data = _post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            {"contents": [{"parts": [{"text": prompt}]}],
             "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}},
            {"x-goog-api-key": key})
        return data["candidates"][0]["content"]["parts"][0]["text"]
    if provider == "openai":
        data = _post(
            "https://api.openai.com/v1/chat/completions",
            {"model": model, "messages": [{"role": "user", "content": prompt}],
             "response_format": {"type": "json_object"}},
            {"Authorization": f"Bearer {key}"})
        return data["choices"][0]["message"]["content"]
    data = _post(
        "https://api.anthropic.com/v1/messages",
        {"model": model, "max_tokens": 400, "temperature": 0,
         "messages": [{"role": "user", "content": prompt}]},
        {"x-api-key": key, "anthropic-version": "2023-06-01"})
    return data["content"][0]["text"]


def _normalize(text):
    return re.sub(r"[\s.,·!?~\"'“”‘’]+", "", text or "")


def parse_response(raw, narrative):
    """LLM 응답을 검증한다. 형식이 틀리거나 근거 인용이 원문에 없으면 점수를 버린다."""
    match = re.search(r"\{.*\}", raw or "", re.S)
    if not match:
        return _result("ERROR", None, "AI 응답 형식을 해석하지 못했습니다.")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return _result("ERROR", None, "AI 응답 형식을 해석하지 못했습니다.")

    score = data.get("score")
    criterion = str(data.get("criterion") or "").strip()
    evidence = str(data.get("evidence") or "").strip()
    missing = str(data.get("missing") or "").strip()

    if score is None:
        reason = f"판단 보류: {missing}" if missing else "판단 보류: 서술에 근거가 부족합니다."
        return _result("ABSTAIN", None, reason)
    if type(score) is not int or not -5 <= score <= 4:
        return _result("ERROR", None, "AI가 RASS 범위를 벗어난 값을 냈습니다.")
    if not evidence or _normalize(evidence) not in _normalize(narrative):
        return _result("ABSTAIN", None,
                       "판단 보류: AI가 제시한 근거가 관찰 서술 원문에 없습니다(환각 차단).")
    return _result("SCORED", score, f"기준 {score:+d} — {criterion}", evidence)


def _result(status, score, reason, evidence=""):
    return {"status": status, "score": score, "reason": reason, "evidence": evidence}


def suggest_rass_ai(narrative, caller=call_llm):
    narrative = (narrative or "").strip()
    if not narrative:
        return _result("ABSTAIN", None, "관찰 서술을 입력해야 AI가 해석할 수 있습니다.")
    if len(narrative) > MAX_NARRATIVE:
        return _result("ABSTAIN", None, f"관찰 서술은 {MAX_NARRATIVE}자 이내로 입력해 주세요.")
    provider = detect_provider()
    if provider is None:
        return _result("UNAVAILABLE", None,
                       "AI API 키가 설정되지 않았습니다. README의 AI 설정을 확인하세요.")
    try:
        raw = caller(provider, build_prompt(narrative))
    except urllib.error.HTTPError as e:
        return _result("ERROR", None, f"AI 서비스 오류 (HTTP {e.code}). 키와 모델 이름을 확인하세요.")
    except Exception as e:
        return _result("ERROR", None, f"AI 서비스에 연결하지 못했습니다 ({type(e).__name__}).")
    return parse_response(raw, narrative)
