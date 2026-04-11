"""
장애 패턴 분석 API
입력: 장애 이력 목록
출력: 빈도 TOP-N, 시간대/요일별 분포, 반복 장애 학교, 예측 위험도
"""
from typing import List, Optional, Dict
from collections import Counter, defaultdict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class IncidentRecord(BaseModel):
    incident_id:   int
    school_id:     int
    school_name:   Optional[str] = None
    incident_type: Optional[str] = None
    occurred_at:   str             # ISO 8601: "2024-03-15T14:30:00"
    resolved_at:   Optional[str] = None
    status:        Optional[str] = None


class PatternRequest(BaseModel):
    incidents:  List[IncidentRecord]
    top_n:      int = 5            # 상위 N개 패턴 반환


class TimeDistribution(BaseModel):
    hour_dist:   Dict[str, int]    # {"0": 3, "1": 1, ...}
    weekday_dist: Dict[str, int]   # {"Mon": 5, "Tue": 3, ...}


class HotSchool(BaseModel):
    school_id:   int
    school_name: Optional[str]
    count:       int
    risk_level:  str               # low | medium | high | critical


class TypePattern(BaseModel):
    incident_type: str
    count:         int
    pct:           float
    avg_resolve_hours: Optional[float]


class PatternResult(BaseModel):
    total_incidents:  int
    analysis_period:  str
    type_patterns:    List[TypePattern]
    time_distribution: TimeDistribution
    hot_schools:      List[HotSchool]
    repeat_threshold: int
    summary:          str


def _parse_hour_weekday(dt_str: str):
    """ISO 날짜 문자열에서 시간(0-23)과 요일(Mon..Sun) 추출"""
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        return dt.hour, weekdays[dt.weekday()]
    except Exception:
        return None, None


def _resolve_hours(start: str, end: str) -> Optional[float]:
    try:
        from datetime import datetime
        s = datetime.fromisoformat(start.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end.replace("Z", "+00:00"))
        diff = (e - s).total_seconds() / 3600
        return round(diff, 1) if diff >= 0 else None
    except Exception:
        return None


@router.post("/incident_pattern", response_model=PatternResult)
def analyze_incident_pattern(req: PatternRequest):
    """
    장애 이력 패턴 분석
    - 유형별 빈도
    - 시간대/요일별 분포
    - 반복 장애 학교 위험도 분류
    """
    incidents = req.incidents
    if not incidents:
        raise HTTPException(status_code=400, detail="장애 이력이 없습니다.")

    total = len(incidents)

    # ── 분석 기간 ─────────────────────────────────────────────
    dates = sorted(r.occurred_at for r in incidents)
    period = f"{dates[0][:10]} ~ {dates[-1][:10]}" if dates else "-"

    # ── 유형별 빈도 ───────────────────────────────────────────
    type_counter: Counter = Counter()
    type_resolve: defaultdict = defaultdict(list)
    for r in incidents:
        t = r.incident_type or "기타"
        type_counter[t] += 1
        if r.resolved_at:
            h = _resolve_hours(r.occurred_at, r.resolved_at)
            if h is not None:
                type_resolve[t].append(h)

    type_patterns = []
    for t, cnt in type_counter.most_common(req.top_n):
        rh_list = type_resolve[t]
        avg_rh = round(sum(rh_list) / len(rh_list), 1) if rh_list else None
        type_patterns.append(TypePattern(
            incident_type=t,
            count=cnt,
            pct=round(cnt / total * 100, 1),
            avg_resolve_hours=avg_rh,
        ))

    # ── 시간대/요일 분포 ─────────────────────────────────────
    hour_counter: Counter = Counter()
    weekday_counter: Counter = Counter()
    for r in incidents:
        h, wd = _parse_hour_weekday(r.occurred_at)
        if h is not None:
            hour_counter[str(h)] += 1
        if wd is not None:
            weekday_counter[wd] += 1

    hour_dist    = {str(i): hour_counter.get(str(i), 0) for i in range(24)}
    weekday_order = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekday_dist = {d: weekday_counter.get(d, 0) for d in weekday_order}

    # ── 반복 장애 학교 ────────────────────────────────────────
    school_counter: Counter = Counter()
    school_name_map: Dict[int, str] = {}
    for r in incidents:
        school_counter[r.school_id] += 1
        if r.school_name:
            school_name_map[r.school_id] = r.school_name

    # 위험도 기준: ≥10=critical, ≥6=high, ≥3=medium, else=low
    def risk_level(cnt: int) -> str:
        if cnt >= 10: return "critical"
        if cnt >= 6:  return "high"
        if cnt >= 3:  return "medium"
        return "low"

    repeat_threshold = 3
    hot_schools = []
    for sid, cnt in school_counter.most_common(req.top_n):
        hot_schools.append(HotSchool(
            school_id=sid,
            school_name=school_name_map.get(sid),
            count=cnt,
            risk_level=risk_level(cnt),
        ))

    # ── 요약 메시지 ───────────────────────────────────────────
    top_type   = type_patterns[0].incident_type if type_patterns else "-"
    top_school = hot_schools[0].school_name or f"학교ID {hot_schools[0].school_id}" if hot_schools else "-"
    critical_cnt = sum(1 for s in hot_schools if s.risk_level == "critical")
    high_cnt     = sum(1 for s in hot_schools if s.risk_level == "high")

    summary_parts = [f"분석 기간: {period}, 총 {total}건."]
    summary_parts.append(f"가장 빈번한 장애 유형: {top_type} ({type_patterns[0].count}건).")
    if hot_schools:
        summary_parts.append(f"반복 장애 학교 상위: {top_school} ({hot_schools[0].count}건).")
    if critical_cnt:
        summary_parts.append(f"위험도 Critical 학교 {critical_cnt}곳 — 즉각 점검 필요.")
    elif high_cnt:
        summary_parts.append(f"위험도 High 학교 {high_cnt}곳 — 우선 점검 권장.")

    return PatternResult(
        total_incidents=total,
        analysis_period=period,
        type_patterns=type_patterns,
        time_distribution=TimeDistribution(hour_dist=hour_dist, weekday_dist=weekday_dist),
        hot_schools=hot_schools,
        repeat_threshold=repeat_threshold,
        summary=" ".join(summary_parts),
    )


@router.post("/incident_pattern/batch")
def batch_pattern(requests: List[PatternRequest]):
    """여러 기간/그룹 일괄 분석"""
    results = []
    for i, req in enumerate(requests):
        try:
            results.append(analyze_incident_pattern(req).model_dump())
        except Exception as e:
            results.append({"index": i, "error": str(e)})
    return results
