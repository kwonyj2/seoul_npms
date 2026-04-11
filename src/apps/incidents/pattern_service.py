"""
장애 패턴 분석 고도화 서비스

기능:
  1. predict_vulnerable_assets  — 학교별 취약 장비 예측 (설치 연도 + 장애 빈도 + 내용연수)
  2. analyze_seasonal_pattern   — 계절별 장애 패턴 분석
  3. analyze_hourly_pattern     — 시간대별 장애 패턴 분석
  4. predict_sla_risk           — SLA 위반 예측 (미완료 장애 위험도)
  5. generate_monthly_insight   — 월간 인사이트 리포트 자동 생성
"""
from datetime import timedelta, datetime

from django.db.models import Count, Q
from django.utils import timezone


# ─────────────────────────────────────────────────────────────
# 1. 학교별 취약 장비 예측
# ─────────────────────────────────────────────────────────────
def predict_vulnerable_assets(center, top_n: int = 20) -> list:
    """학교별 취약 장비 예측

    취약도 점수 = (노후 장비 수 × 3) + (장애 빈도) + (노후 장비 비율 × 2)

    Args:
        center: SupportCenter 인스턴스
        top_n: 반환할 최대 학교 수

    Returns: [{'school': name, 'school_id': pk, 'asset_count': N,
               'overdue_count': N, 'incident_count': N,
               'vulnerability_score': F}, ...]
    """
    from apps.assets.models import Asset, AssetCategory
    from apps.incidents.models import Incident

    current_year = timezone.localdate().year
    schools = center.schools.all()

    result = []
    for school in schools:
        # 설치 장비 목록
        assets = Asset.objects.filter(
            current_school=school, status='installed'
        ).select_related('asset_model__category')

        asset_count = assets.count()

        # 내용연수 초과 장비 수
        overdue_count = 0
        for asset in assets:
            if asset.install_year:
                usable = asset.asset_model.category.usable_years
                age = current_year - asset.install_year
                if age > usable:
                    overdue_count += 1

        # 장애 빈도 (최근 1년)
        one_year_ago = timezone.now() - timedelta(days=365)
        incident_count = Incident.objects.filter(
            school=school,
            received_at__gte=one_year_ago,
        ).count()

        # 취약도 점수
        overdue_ratio = (overdue_count / asset_count) if asset_count > 0 else 0
        score = (overdue_count * 3) + incident_count + (overdue_ratio * 2 * 10)

        result.append({
            'school':              school.name,
            'school_id':           school.pk,
            'asset_count':         asset_count,
            'overdue_count':       overdue_count,
            'incident_count':      incident_count,
            'vulnerability_score': round(score, 2),
        })

    result.sort(key=lambda x: x['vulnerability_score'], reverse=True)
    return result[:top_n]


# ─────────────────────────────────────────────────────────────
# 2. 계절별 장애 패턴 분석
# ─────────────────────────────────────────────────────────────
def analyze_seasonal_pattern(qs) -> list:
    """계절별 장애 발생 건수 및 비율

    봄(3~5월), 여름(6~8월), 가을(9~11월), 겨울(12~2월)

    Returns: [{'season': '봄', 'months': '3~5월', 'count': N, 'ratio': F}, ...]
    """
    SEASONS = [
        {'season': '봄',   'months': '3~5월',  'month_range': [3, 4, 5]},
        {'season': '여름', 'months': '6~8월',  'month_range': [6, 7, 8]},
        {'season': '가을', 'months': '9~11월', 'month_range': [9, 10, 11]},
        {'season': '겨울', 'months': '12~2월', 'month_range': [12, 1, 2]},
    ]

    counts = {s['season']: 0 for s in SEASONS}
    for received_at in qs.values_list('received_at', flat=True):
        if received_at:
            local_dt = timezone.localtime(received_at)
            m = local_dt.month
            for s in SEASONS:
                if m in s['month_range']:
                    counts[s['season']] += 1
                    break

    total = sum(counts.values()) or 1
    return [
        {
            'season': s['season'],
            'months': s['months'],
            'count':  counts[s['season']],
            'ratio':  round(counts[s['season']] / total * 100, 1),
        }
        for s in SEASONS
    ]


# ─────────────────────────────────────────────────────────────
# 3. 시간대별 장애 패턴 분석
# ─────────────────────────────────────────────────────────────
def analyze_hourly_pattern(qs) -> list:
    """시간대별(0~23) 장애 발생 건수

    Returns: [{'hour': 0, 'count': N}, ..., {'hour': 23, 'count': N}]
    """
    counts = {h: 0 for h in range(24)}
    for received_at in qs.values_list('received_at', flat=True):
        if received_at:
            local_dt = timezone.localtime(received_at)
            counts[local_dt.hour] += 1
    return [{'hour': h, 'count': counts[h]} for h in range(24)]


# ─────────────────────────────────────────────────────────────
# 4. SLA 위반 예측
# ─────────────────────────────────────────────────────────────
def predict_sla_risk(center, threshold: float = 0) -> list:
    """미완료 장애의 SLA 위반 위험도 실시간 계산

    위험도(%) = 경과시간 / SLA 기준시간 × 100

    Args:
        center: SupportCenter 인스턴스
        threshold: 이 값 이상인 장애만 반환 (0이면 전체)

    Returns: [{'incident_number': str, 'school': str,
               'arrival_risk_pct': F, 'resolve_risk_pct': F,
               'status': str}, ...]
    """
    from apps.incidents.models import Incident, IncidentSLA
    from django.conf import settings

    ACTIVE_STATUSES = ['received', 'assigned', 'moving', 'arrived', 'processing']
    now = timezone.now()

    # SLA 기준 (시스템 설정 또는 기본값)
    arrival_hours = getattr(settings, 'SLA_ARRIVAL_HOURS', 2)
    resolve_hours = getattr(settings, 'SLA_RESOLVE_HOURS', 8)

    active_qs = Incident.objects.filter(
        school__support_center=center,
        status__in=ACTIVE_STATUSES,
    ).select_related('school')

    result = []
    for inc in active_qs:
        elapsed_min = (now - inc.received_at).total_seconds() / 60

        # IncidentSLA가 있으면 해당 target 사용, 없으면 설정값 기반 계산
        try:
            sla_obj = inc.sla
            arrival_target_min = (sla_obj.arrival_target - inc.received_at).total_seconds() / 60
            resolve_target_min = (sla_obj.resolve_target - inc.received_at).total_seconds() / 60
        except Exception:
            arrival_target_min = arrival_hours * 60
            resolve_target_min = resolve_hours * 60

        arrival_risk = round(elapsed_min / arrival_target_min * 100, 1) if arrival_target_min > 0 else 0
        resolve_risk = round(elapsed_min / resolve_target_min * 100, 1) if resolve_target_min > 0 else 0

        max_risk = max(arrival_risk, resolve_risk)
        if max_risk >= threshold:
            result.append({
                'incident_number': inc.incident_number,
                'school':          inc.school.name,
                'status':          inc.status,
                'elapsed_min':     round(elapsed_min, 1),
                'arrival_risk_pct': min(arrival_risk, 999),
                'resolve_risk_pct': min(resolve_risk, 999),
            })

    result.sort(key=lambda x: x['arrival_risk_pct'], reverse=True)
    return result


# ─────────────────────────────────────────────────────────────
# 5. 월간 인사이트 리포트 자동 생성
# ─────────────────────────────────────────────────────────────
def generate_monthly_insight(center, year: int, month: int) -> dict:
    """월간 인사이트 리포트 자동 생성

    Args:
        center: SupportCenter 인스턴스
        year, month: 집계 기준 연월

    Returns:
        {
          'period': '2026년 4월',
          'summary': {total_incidents, completed, sla_arrival_rate, sla_resolve_rate},
          'hourly':  [...],
          'seasonal': [...],
          'hotspots': [...],
          'vulnerable_assets': [...],
          'recommendations': [...],
        }
    """
    from apps.incidents.models import Incident

    # 기간 설정
    start = timezone.make_aware(datetime(year, month, 1))
    if month == 12:
        end = timezone.make_aware(datetime(year + 1, 1, 1))
    else:
        end = timezone.make_aware(datetime(year, month + 1, 1))

    qs = Incident.objects.filter(
        school__support_center=center,
        received_at__gte=start,
        received_at__lt=end,
    )

    total = qs.count()
    completed = qs.filter(status='completed').count()
    sla_arrival_ok = qs.filter(sla_arrival_ok=True).count()
    sla_resolve_ok = qs.filter(sla_resolve_ok=True).count()

    sla_arrival_rate = round(sla_arrival_ok / total * 100, 1) if total else 0.0
    sla_resolve_rate = round(sla_resolve_ok / total * 100, 1) if total else 0.0

    # 재발 핫스팟 (학교+카테고리)
    hotspot_rows = (
        qs.filter(category__isnull=False)
        .values('school__name', 'category__name')
        .annotate(count=Count('id'))
        .filter(count__gte=2)
        .order_by('-count')[:5]
    )
    hotspots = [
        {'school': r['school__name'], 'category': r['category__name'], 'count': r['count']}
        for r in hotspot_rows
    ]

    # 취약 장비
    vulnerable = predict_vulnerable_assets(center, top_n=5)

    # 자동 권고사항 생성
    recommendations = []
    if sla_arrival_rate < 80:
        recommendations.append(
            f'도착 SLA 준수율({sla_arrival_rate}%)이 80% 미만입니다. 인력 배정 체계를 점검하세요.'
        )
    if sla_resolve_rate < 80:
        recommendations.append(
            f'처리 SLA 준수율({sla_resolve_rate}%)이 80% 미만입니다. 처리 절차 개선이 필요합니다.'
        )
    for v in vulnerable:
        if v['overdue_count'] > 0:
            recommendations.append(
                f'{v["school"]}에 내용연수 초과 장비 {v["overdue_count"]}대 — 교체 계획 수립 권고.'
            )
    for h in hotspots:
        recommendations.append(
            f'{h["school"]} {h["category"]} 장애가 {h["count"]}건으로 반복 발생 — 근본 원인 분석 필요.'
        )
    if not recommendations:
        recommendations.append('이번 달 특이사항 없음. 현행 운영 수준 유지하세요.')

    return {
        'period':            f'{year}년 {month}월',
        'center':            center.name,
        'summary': {
            'total_incidents':   total,
            'completed':         completed,
            'sla_arrival_rate':  sla_arrival_rate,
            'sla_resolve_rate':  sla_resolve_rate,
        },
        'hourly':            analyze_hourly_pattern(qs),
        'seasonal':          analyze_seasonal_pattern(qs),
        'hotspots':          hotspots,
        'vulnerable_assets': vulnerable,
        'recommendations':   recommendations,
    }
