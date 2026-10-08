# OBSERVATION_OPTIONS: (표시 텍스트, RASS 점수) 순서로 정의
OBSERVATION_OPTIONS = [
    ("환자가 폭력적이며 의료진에게 즉각적인 위험이 있음", 4),
    ("튜브나 카테터를 당기며 의료진에게 공격적임", 3),
    ("목적 없는 움직임이 잦거나 인공호흡기에 저항함", 2),
    ("불안하거나 초조하지만 공격적이지 않음", 1),
    ("깨어 있고 차분함", 0),
    ("목소리에 눈을 뜨고 10초 이상 눈맞춤을 유지함", -1),
    ("목소리에 잠깐 눈을 뜨지만 눈맞춤이 10초 미만임", -2),
    ("목소리에 움직이거나 눈을 뜨지만 눈맞춤은 없음", -3),
    ("목소리에는 반응하지 않고 신체 자극에 움직임", -4),
    ("목소리와 신체 자극 모두에 반응이 없음", -5),
]


def calculate_cam_icu(rass_score, f1=None, f2=None, f3=None, f4=None):
    """공식: F1 AND F2 AND (F3 OR F4). 서버에서만 계산한다."""
    if not isinstance(rass_score, int) or not -5 <= rass_score <= 4:
        raise ValueError("RASS 점수는 -5부터 +4 사이의 정수여야 합니다.")
    if rass_score <= -4:
        return "UNASSESSABLE"
    features = (f1, f2, f3, f4)
    if any(type(value) is not bool for value in features):
        raise ValueError("CAM-ICU 특징 1~4를 모두 선택해야 합니다.")
    return "POSITIVE" if f1 and f2 and (f3 or f4) else "NEGATIVE"


def suggest_rass_by_index(index):
    """선택형 관찰 항목 인덱스를 기반으로 참고 RASS 제안."""
    if not isinstance(index, int) or not 0 <= index < len(OBSERVATION_OPTIONS):
        raise ValueError("유효하지 않은 관찰 항목 인덱스입니다.")
    text, score = OBSERVATION_OPTIONS[index]
    return {
        "status": "SCORED",
        "score": score,
        "reason": f"선택한 관찰 항목을 기반으로 한 참고 제안입니다.",
    }


def suggest_rass(observation):
    """하위 호환성 유지용 텍스트 기반 제안. 최종 RASS는 간호사가 직접 확정한다."""
    text = (observation or "").strip().lower()
    if not text:
        return {"status": "ABSTAIN", "score": None, "reason": "관찰 기록이 없어 제안하지 않았습니다."}
    rules = [
        (("반응 없음", "무반응", "깨우지 못"), -5),
        (("신체 자극", "통증 자극"), -4),
        (("목소리", "눈을 뜸", "움직임"), -3),
        (("짧게 눈맞춤", "10초 미만"), -2),
        (("10초 이상", "지속적 눈맞춤"), -1),
        (("차분", "명료", "정상"), 0),
        (("불안", "초조"), 1),
        (("빈번한 움직임", "인공호흡기 저항"), 2),
        (("튜브를 당김", "공격적"), 3),
        (("폭력", "즉각 위험"), 4),
    ]
    for words, score in rules:
        if any(word in text for word in words):
            return {"status": "SCORED", "score": score, "reason": "관찰 기록의 표현을 참고한 시연용 제안입니다."}
    return {"status": "ABSTAIN", "score": None, "reason": "점수를 제안할 근거가 충분하지 않습니다."}
