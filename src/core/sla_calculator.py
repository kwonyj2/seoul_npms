"""
SLA 월간 지표 자동 계산 (서울특별시교육청 서비스수준협약서 기준)

9개 지표, 가중치 합 100%:
  운영관리  — 장비가동률(20%), 예방점검준수율(10%)
  장애관리  — 평균장애시간(10%), 장애건수(10%), 초과건수(10%), 인적장애(10%), 반복장애(10%)
  정보보안  — 보안위규건수(10%)
  서비스지원 — 서비스만족도(10%)
"""

import calendar
from datetime import datetime, date, timedelta

from django.utils import timezone
from django.db.models import Avg, Count, Sum, Q


# ─────────────────────────────────────────────
# 개별 지표 점수 계산 함수
# ─────────────────────────────────────────────

def score_uptime(pct: float) -> float:
    """
    장비 가동률 점수 (A~F 6단계)
    A(100) ≥99.98%, B(80) 99.85~99.98%, C(60) 98.8889~99.85%,
    D(40) 98.3333~98.8889%, E(20) 96.6667~98.3333%, F(0) <96.6667%
    """
    if pct >= 99.98:   return 100.0
    if pct >= 99.85:   return 80.0
    if pct >= 98.8889: return 60.0
    if pct >= 98.3333: return 40.0
    if pct >= 96.6667: return 20.0
    return 0.0


def score_inspection(pct: float) -> float:
    """
    예방점검 준수율 점수 (A~F 5단계)
    A(100) 100%, B(90) 99.1~100%, C(80) 97.9~99.1%, D(70) 97~97.9%, F(60) <97%
    """
    if pct >= 100.0: return 100.0
    if pct >= 99.1:  return 90.0
    if pct >= 97.9:  return 80.0
    if pct >= 97.0:  return 70.0
    return 60.0


def score_avg_fault_min(avg_min: float) -> float:
    """
    평균 장애시간 점수
    A(100) ≤240분, B(90) 241~312분, C(80) 313~408분, D(70) 409~480분, F(60) >480분
    """
    if avg_min <= 240: return 100.0
    if avg_min <= 312: return 90.0
    if avg_min <= 408: return 80.0
    if avg_min <= 480: return 70.0
    return 60.0


def score_fault_count(cnt: int) -> float:
    """
    장애건수 점수
    A(100) ≤5건, B(90) 6~10건, C(80) 11~20건, D(70) 21~30건, F(60) >30건
    """
    if cnt <= 5:  return 100.0
    if cnt <= 10: return 90.0
    if cnt <= 20: return 80.0
    if cnt <= 30: return 70.0
    return 60.0


def score_overtime(cnt: int) -> float:
    """
    장애조치 최대 허용시간 초과 건수 점수
    A(100) 0건, C(80) 1건, F(60) 2건+
    """
    if cnt == 0: return 100.0
    if cnt == 1: return 80.0
    return 60.0


def score_human_error(cnt: int) -> float:
    """
    인적장애 건수 점수
    A(100) 0건, C(80) 1건, F(60) 2건+
    """
    if cnt == 0: return 100.0
    if cnt == 1: return 80.0
    return 60.0


def score_recurrence(cnt: int) -> float:
    """
    반복장애 건수 점수
    A(100) ≤3건, C(80) 4~5건, F(60) 6건+
    """
    if cnt <= 3: return 100.0
    if cnt <= 5: return 80.0
    return 60.0


def score_security(cnt: int) -> float:
    """
    보안위규 건수 점수
    A(100) 0건, C(80) 1건, F(60) 2건+
    """
    if cnt == 0: return 100.0
    if cnt == 1: return 80.0
    return 60.0


def score_satisfaction(pct: float) -> float:
    """
    서비스 만족도 점수
    A(100) 100%, B(90) 99.1~100%, C(80) 97.9~99.1%, D(70) 97~97.9%, F(60) <97%
    """
    if pct >= 100.0: return 100.0
    if pct >= 99.1:  return 90.0
    if pct >= 97.9:  return 80.0
    if pct >= 97.0:  return 70.0
    return 60.0


def grade_from_score(total: float) -> str:
    """종합점수 → 평가등급 (탁월/우수/보통/미흡/불량)"""
    if total >= 95: return 'excellent'
    if total >= 90: return 'good'
    if total >= 85: return 'normal'
    if total >= 80: return 'poor'
    return 'bad'


# ─────────────────────────────────────────────
# 월간 지표 자동 계산
# ─────────────────────────────────────────────

def calculate_monthly(year: int, month: int, security_count: int = 0,
                       security_note: str = '') -> dict:
    """
    year/month 에 해당하는 월간 SLA 9개 지표를 DB에서 자동 계산하여 dict 반환.
    보안위규 건수는 수동 입력값(security_count)을 사용.
    반환값을 SLAMonthly 모델에 저장하면 됨.
    """
    from apps.incidents.models import Incident, IncidentSLA
    from apps.progress.models import InspectionPlan, SchoolInspection

    # 해당 월 범위
    first_day = date(year, month, 1)
    last_day  = date(year, month, calendar.monthrange(year, month)[1])
    month_start = datetime(year, month, 1, 0, 0, 0,
                           tzinfo=timezone.get_current_timezone())
    month_end   = datetime(year, month, last_day.day, 23, 59, 59,
                           tzinfo=timezone.get_current_timezone())

    result = {
        'year': year, 'month': month,
        'security_count': security_count,
        'security_note':  security_note,
    }

    # ──────────────────────────────────────────
    # 1. 장비 가동률
    # 월 가동시간 = 계약일수 × 24h × 60min
    # ──────────────────────────────────────────
    total_min = last_day.day * 24 * 60
    # 해당 월 완료된 장애(서비스 중단)의 조치시간 합산
    # completed_at 기준 월 귀속 (협약서 특이사항)
    fault_min = 0
    sla_qs = IncidentSLA.objects.filter(
        resolve_actual__year=year,
        resolve_actual__month=month,
        incident__fault_type='service_stop',
    )
    for sla in sla_qs:
        inc = sla.incident
        if inc.received_at and sla.resolve_actual:
            diff = (sla.resolve_actual - inc.received_at).total_seconds() / 60
            fault_min += max(0, diff)
    fault_min = int(fault_min)

    maint_min = 0  # 계획작업(예방점검 등) 서비스중단 시간 — 별도 입력 없으면 0
    uptime_pct = None
    if (total_min - maint_min) > 0:
        uptime_pct = ((total_min - maint_min - fault_min)
                      / (total_min - maint_min)) * 100
        uptime_pct = round(uptime_pct, 4)

    result.update({
        'uptime_total_min': total_min,
        'uptime_fault_min': fault_min,
        'uptime_maint_min': maint_min,
        'uptime_pct':   uptime_pct,
        'uptime_score': score_uptime(uptime_pct) if uptime_pct is not None else 100.0,
    })

    # ──────────────────────────────────────────
    # 2. 예방점검 준수율
    # progress 앱 InspectionPlan 기준
    # ──────────────────────────────────────────
    plans = InspectionPlan.objects.filter(
        start_date__lte=last_day,
        end_date__gte=first_day,
    )
    insp_total     = 0
    insp_completed = 0
    for plan in plans:
        schools = SchoolInspection.objects.filter(plan=plan)
        insp_total     += schools.count()
        insp_completed += schools.filter(status='completed').count()

    insp_pct = None
    if insp_total > 0:
        insp_pct = round(insp_completed / insp_total * 100, 2)
    insp_score = score_inspection(insp_pct) if insp_pct is not None else 100.0

    result.update({
        'inspection_total':     insp_total,
        'inspection_completed': insp_completed,
        'inspection_pct':   insp_pct,
        'inspection_score': insp_score,
    })

    # ──────────────────────────────────────────
    # 3~7. 장애 관련 지표
    # 복구 완료시간(completed_at) 기준 월 귀속
    # ──────────────────────────────────────────
    inc_qs = Incident.objects.filter(
        completed_at__year=year,
        completed_at__month=month,
        status='completed',
    ).exclude(fault_type__in=['', 'other']
    ).exclude(category__code__in=['inquiry', 'network_work'])

    fault_count = inc_qs.count()

    # 평균 장애시간 (업무시간 기준 — sla_utils 사용)
    total_fault_min_sum = 0
    overtime_count      = 0
    for inc in inc_qs:
        if inc.received_at and inc.completed_at:
            try:
                from core.sla_utils import business_hours_elapsed_minutes
                biz_min = business_hours_elapsed_minutes(inc.received_at,
                                                          inc.completed_at)
            except Exception:
                biz_min = (inc.completed_at - inc.received_at).total_seconds() / 60
            total_fault_min_sum += biz_min
            if biz_min > 480:   # 장애조치 최대 허용시간 480분
                overtime_count += 1

    avg_fault_min = round(total_fault_min_sum / fault_count, 1) if fault_count else None

    human_error_count = inc_qs.filter(is_human_error=True).count()
    recurrence_count  = inc_qs.filter(is_recurrence=True).count()

    result.update({
        'fault_count':       fault_count,
        'fault_count_score': score_fault_count(fault_count),
        'avg_fault_min':     avg_fault_min,
        'avg_fault_score':   score_avg_fault_min(avg_fault_min) if avg_fault_min is not None else 100.0,
        'overtime_count':    overtime_count,
        'overtime_score':    score_overtime(overtime_count),
        'human_error_count': human_error_count,
        'human_error_score': score_human_error(human_error_count),
        'recurrence_count':  recurrence_count,
        'recurrence_score':  score_recurrence(recurrence_count),
    })

    # ──────────────────────────────────────────
    # 8. 보안위규 (수동 입력)
    # ──────────────────────────────────────────
    result['security_score'] = score_security(security_count)

    # ──────────────────────────────────────────
    # 9. 서비스 만족도
    # satisfaction_score 평균 (1~5점 → %)
    # 협약서: 만족도점수 합계 ÷ 응답건수
    # ──────────────────────────────────────────
    sat_qs = Incident.objects.filter(
        completed_at__year=year,
        completed_at__month=month,
        satisfaction_score__isnull=False,
    )
    sat_count = sat_qs.count()
    sat_pct   = None
    if sat_count > 0:
        avg_score = sat_qs.aggregate(a=Avg('satisfaction_score'))['a'] or 0
        sat_pct   = round(avg_score / 5 * 100, 2)   # 5점 만점 → %

    result.update({
        'satisfaction_count': sat_count,
        'satisfaction_pct':   sat_pct,
        'satisfaction_score': score_satisfaction(sat_pct) if sat_pct is not None else 100.0,
    })

    # ──────────────────────────────────────────
    # 종합점수 (가중치 적용)
    # ──────────────────────────────────────────
    WEIGHTS = {
        'uptime':       0.20,
        'inspection':   0.10,
        'avg_fault':    0.10,
        'fault_count':  0.10,
        'overtime':     0.10,
        'human_error':  0.10,
        'recurrence':   0.10,
        'security':     0.10,
        'satisfaction': 0.10,
    }
    total = (
        result['uptime_score']       * WEIGHTS['uptime'] +
        result['inspection_score']   * WEIGHTS['inspection'] +
        result['avg_fault_score']    * WEIGHTS['avg_fault'] +
        result['fault_count_score']  * WEIGHTS['fault_count'] +
        result['overtime_score']     * WEIGHTS['overtime'] +
        result['human_error_score']  * WEIGHTS['human_error'] +
        result['recurrence_score']   * WEIGHTS['recurrence'] +
        result['security_score']     * WEIGHTS['security'] +
        result['satisfaction_score'] * WEIGHTS['satisfaction']
    )
    total = round(total, 2)
    result['total_score'] = total
    result['grade']       = grade_from_score(total)
    result['calculated_at'] = timezone.now()

    return result


def save_monthly(year: int, month: int, user=None,
                 security_count: int = 0, security_note: str = '',
                 memo: str = ''):
    """
    calculate_monthly 결과를 SLAMonthly 모델에 upsert.
    이미 존재하면 갱신, 없으면 생성.
    """
    from apps.incidents.models import SLAMonthly
    data = calculate_monthly(year, month, security_count, security_note)
    data['memo']       = memo
    data['created_by'] = user

    obj, created = SLAMonthly.objects.update_or_create(
        year=year, month=month,
        defaults=data,
    )
    return obj, created
