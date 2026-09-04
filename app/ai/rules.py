"""Mock 어댑터가 사용하는 결정적 규칙 엔진.

한 줄(문장) 단위로 규칙을 매칭해 상태·위험신호·미해결 이슈·추천 Action 을 만든다.
LLM 을 붙이더라도 이 규칙표는 프롬프트의 카테고리 정의와 후처리 검증에 그대로 쓸 수 있다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rule:
    key: str
    all_of: tuple[str, ...] = ()
    any_of: tuple[str, ...] = ()
    none_of: tuple[str, ...] = ()
    category: str | None = None  # client_status 소문자 키
    status: str | None = None
    main: str | None = None
    risk: tuple[str, str, str] | None = None  # (type, severity, description)
    issue: str | None = None
    # (action_type, title, priority, reason, due_in_days)
    actions: tuple[tuple[str, str, str, str, int | None], ...] = ()


RULES: tuple[Rule, ...] = (
    # --- 안전 / 학대 (가장 먼저 판정) ---
    Rule(
        key="safety_fall",
        any_of=("넘어졌", "넘어져", "쓰러졌", "다쳤"),
        category="health",
        status="낙상 등 안전사고 확인 필요",
        main="낙상 또는 부상 관련 언급",
        risk=("SAFETY", "HIGH", "안전사고 발생 여부 즉시 확인 필요"),
        issue="낙상 경위 및 현재 상태 확인 필요",
        actions=(("HOME_VISIT", "가정 방문으로 안전 상태 확인", "HIGH", "낙상 또는 부상 관련 언급이 있어 직접 확인이 필요함", 1),),
    ),
    Rule(
        key="abuse",
        any_of=("때려", "맞았", "욕을 하", "돈을 가져가"),
        category="emotion",
        status="대인관계 안전 확인 필요",
        main="대인관계 관련 우려 언급",
        risk=("ABUSE", "HIGH", "대인관계 안전 상태 추가 확인 필요"),
        issue="대인관계 안전 확인 필요",
        actions=(("CASE_REVIEW", "사례회의를 통한 개입 방향 검토", "HIGH", "추가 확인이 필요한 안전 관련 언급이 있음", 2),),
    ),
    # --- 건강 ---
    Rule(
        key="knee_worse",
        all_of=("무릎",),
        any_of=("너무", "심해", "심하", "악화", "많이 아", "더 아"),
        category="health",
        status="무릎 통증 악화",
        main="무릎 통증 악화",
        risk=("HEALTH", "MEDIUM", "건강 상태 악화 여부 확인 필요"),
        actions=(("CHECK_HEALTH", "통증 및 건강 상태 재확인", "MEDIUM", "무릎 통증이 이전보다 심해졌다고 이야기함", 7),),
    ),
    Rule(
        key="knee_mild",
        all_of=("무릎",),
        any_of=("조금", "약간", "경미"),
        category="health",
        status="경미한 무릎 통증",
        main="경미한 무릎 통증",
    ),
    Rule(
        key="knee",
        all_of=("무릎",),
        category="health",
        status="무릎 통증 지속",
        main="무릎 통증 지속",
    ),
    Rule(
        key="hospital_alone",
        all_of=("병원",),
        any_of=("혼자", "동행", "가기 힘", "가기 어려", "데려다"),
        main="혼자 병원에 가는 데 어려움 호소",
        issue="병원 이동 방법 미정",
        actions=(
            (
                "RESOURCE_REFERRAL",
                "병원 동행 지원 가능 여부 확인",
                "HIGH",
                "진료 예정이나 혼자 이동하기 어렵다고 이야기함",
                3,
            ),
            (
                "FOLLOW_UP_CALL",
                "병원 방문 이후 상태 확인",
                "MEDIUM",
                "진료 결과에 따라 지원 계획을 조정할 필요가 있음",
                10,
            ),
        ),
    ),
    Rule(
        key="hospital_plan",
        all_of=("병원",),
        any_of=("가야", "예약", "다음 주", "진료"),
        main="다음 진료 방문 예정",
        issue="다음 진료 결과 확인 필요",
    ),
    # --- 식생활 ---
    Rule(
        key="meal_once",
        any_of=("한 끼", "한끼", "하루에 한", "한 번 먹", "한번 먹"),
        category="nutrition",
        status="하루 한 끼 수준으로 식사 감소",
        main="하루 한 끼 수준으로 식사 횟수 감소",
        risk=("NUTRITION", "MEDIUM", "식생활 상태 추가 확인 필요"),
        issue="식사지원 서비스 이용 여부 미정",
        actions=(("CHECK_NUTRITION", "식생활 상태 재확인", "HIGH", "식사 횟수가 줄었다고 이야기함", 3),),
    ),
    Rule(
        key="instant_food",
        any_of=("라면", "빵으로 때", "대충 먹"),
        category="nutrition",
        status="식사 준비 어려움",
        main="식사 준비가 어려워 간편식으로 대체",
        risk=("NUTRITION", "MEDIUM", "식생활 상태 추가 확인 필요"),
        issue="식사지원 서비스 이용 여부 미정",
        actions=(("CHECK_NUTRITION", "식생활 상태 재확인", "HIGH", "식사 준비의 어려움을 호소함", 3),),
    ),
    Rule(
        key="meal_hard",
        any_of=("해먹기", "밥 해", "밥하기", "식사 준비", "요리"),
        none_of=("괜찮", "잘 하", "잘하"),
        category="nutrition",
        status="식사 준비 어려움",
        main="식사 준비 어려움",
        risk=("NUTRITION", "MEDIUM", "식생활 상태 추가 확인 필요"),
        actions=(("CHECK_NUTRITION", "식생활 상태 재확인", "HIGH", "식사 준비의 어려움을 호소함", 3),),
    ),
    Rule(
        key="meal_ok",
        any_of=("식사는 잘", "밥은 잘", "식사 잘", "잘 챙겨 먹", "식사 정상"),
        none_of=("못", "안 ", "어렵"),
        category="nutrition",
        status="식사 정상",
        main="식사는 정상적으로 유지",
    ),
    # --- 사회활동 ---
    Rule(
        key="outing_down",
        any_of=("안 나가", "안나가", "못 나가", "나가지를 못", "외출이 줄", "외출 감소", "거의 안"),
        category="social",
        status="외출 감소",
        main="외출 빈도 감소",
        risk=("ISOLATION", "LOW", "사회적 고립 여부 확인 필요"),
    ),
    Rule(
        key="outing_ok",
        any_of=("자주 나", "밖에는 자주", "경로당", "외출 유지", "잘 나가"),
        none_of=("안 ", "못 "),
        category="social",
        status="외출 유지",
        main="외출 유지",
    ),
    # --- 정서 ---
    Rule(
        key="emotion_low",
        any_of=("아무것도 하기 싫", "우울", "외로", "눈물", "잠이 안", "사는 게"),
        category="emotion",
        status="정서 상태 확인 필요",
        main="정서 상태 관련 표현 확인",
        risk=("EMOTION", "MEDIUM", "정서 상태 추가 확인 필요"),
        actions=(("FOLLOW_UP_CALL", "정서 상태 확인을 위한 안부전화", "MEDIUM", "정서 상태와 관련된 표현이 확인됨", 7),),
    ),
    # --- 가족 ---
    Rule(
        key="family_far",
        any_of=("딸", "아들", "자녀", "며느리"),
        category="family",
        status="자녀 타지역 거주",
        main="자녀가 타지역에 거주",
        # 지역/거리 표현이 함께 있어야 한다
        all_of=(),
    ),
    # --- 주거 ---
    Rule(
        key="housing",
        any_of=("보일러", "난방", "집이 추", "곰팡이", "수도가"),
        category="housing",
        status="주거 환경 확인 필요",
        main="주거 환경 관련 언급",
        risk=("HOUSING", "LOW", "주거 환경 추가 확인 필요"),
        issue="주거 환경 개선 필요 여부 미확인",
    ),
    # --- 경제 ---
    Rule(
        key="economic",
        any_of=("생활비", "돈이 없", "공과금", "약값이"),
        category="housing",
        status="경제 상태 확인 필요",
        main="경제적 부담 관련 언급",
        risk=("ECONOMIC", "MEDIUM", "경제 상태 추가 확인 필요"),
        actions=(("RESOURCE_REFERRAL", "경제적 지원 제도 안내 가능 여부 확인", "MEDIUM", "경제적 부담과 관련된 언급이 있음", 7),),
    ),
)

# family_far 규칙은 지역 표현이 함께 있을 때만 적용한다.
_FAMILY_DISTANCE = ("멀리", "타지", "타 지역", "떨어져", "부산", "서울", "대구", "광주", "대전", "울산", "제주", "지방")

_SENTENCE_SPLIT = re.compile(r"[\n.!?。]+")


@dataclass
class Match:
    rule: Rule
    line: str


def split_lines(text: str) -> list[str]:
    """전사문/상담일지 텍스트를 문장 단위로 나눈다."""
    out: list[str] = []
    for raw in _SENTENCE_SPLIT.split(text or ""):
        line = raw.strip().lstrip("-•").strip()
        if line:
            out.append(line)
    return out


_SPEAKER = re.compile(r"^\s*([^:：\n]{1,20})\s*[:：]\s*(.*)$")
_WORKER_LABELS = ("사회복지사", "상담사", "상담원", "복지사", "worker", "counselor")


def client_lines(transcript: str) -> list[str]:
    """화자 라벨이 있으면 내담자 발화만, 없으면 전체 문장을 반환한다."""
    if not transcript:
        return []

    labelled = False
    collected: list[str] = []
    current_is_client = True

    for raw in (transcript or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _SPEAKER.match(line)
        if m:
            labelled = True
            speaker = m.group(1).strip()
            current_is_client = not any(w in speaker.lower() or w in speaker for w in _WORKER_LABELS)
            rest = m.group(2).strip()
            if current_is_client and rest:
                collected.extend(split_lines(rest))
            continue
        if current_is_client:
            collected.extend(split_lines(line))

    if not labelled:
        return split_lines(transcript)
    return collected


def _matches(rule: Rule, line: str) -> bool:
    if rule.all_of and not all(token in line for token in rule.all_of):
        return False
    if rule.any_of and not any(token in line for token in rule.any_of):
        return False
    if rule.none_of and any(token in line for token in rule.none_of):
        return False
    if rule.key == "family_far" and not any(token in line for token in _FAMILY_DISTANCE):
        return False
    return True


def match_rules(lines: list[str]) -> list[Match]:
    """규칙 순서를 유지하며 (규칙, 최초 매칭 문장) 목록을 반환한다."""
    seen: set[str] = set()
    matches: list[Match] = []
    for rule in RULES:
        if rule.key in seen:
            continue
        for line in lines:
            if _matches(rule, line):
                matches.append(Match(rule=rule, line=line))
                seen.add(rule.key)
                break
    return _suppress_overlaps(matches)


_OVERLAP_GROUPS: tuple[tuple[str, ...], ...] = (
    ("knee_worse", "knee_mild", "knee"),  # 더 구체적인 규칙만 남긴다
    ("meal_once", "instant_food", "meal_hard", "meal_ok"),
    ("outing_down", "outing_ok"),
)


def _suppress_overlaps(matches: list[Match]) -> list[Match]:
    keys = {m.rule.key for m in matches}
    drop: set[str] = set()
    for group in _OVERLAP_GROUPS:
        present = [k for k in group if k in keys]
        if len(present) > 1:
            drop.update(present[1:])
    return [m for m in matches if m.rule.key not in drop]


def find_evidence(rule: Rule, transcript_lines: list[str]) -> str | None:
    """확정 전사문에서 해당 규칙을 뒷받침하는 내담자 발화를 찾는다. 없으면 None."""
    for line in transcript_lines:
        if _matches(rule, line):
            return line
    return None


# --- 상태 문구 극성 사전 (변화 감지에 사용) ---
_NEGATIVE = {
    "악화": -2,
    "감소": -2,
    "어려움": -2,
    "어려": -2,
    "곤란": -2,
    "고립": -2,
    "불가": -2,
    "통증": -1,
    "확인 필요": -1,
    "미확인": -1,
    "필요": -1,
}
_POSITIVE = {
    "호전": 2,
    "개선": 2,
    "정상": 1,
    "유지": 1,
    "양호": 1,
    "가능": 1,
}


def phrase_score(phrase: str) -> int:
    scores = [v for k, v in _NEGATIVE.items() if k in phrase]
    scores += [v for k, v in _POSITIVE.items() if k in phrase]
    if not scores:
        return 0
    return min(scores)


def category_score(items: list[str]) -> int | None:
    if not items:
        return None
    return min(phrase_score(item) for item in items)
