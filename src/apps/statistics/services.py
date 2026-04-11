# statistics 비즈니스 로직
from datetime import date, timedelta

from django.db.models import Count, Avg, Q, F
from django.utils import timezone


# ─────────────────────────────────────────────────────────────
# 1. aggregate_daily
# ─────────────────────────────────────────────────────────────
def aggregate_daily(target_date: date):
    """target_date 하루치 장애 통계를 집계해 StatisticsDaily에 저장(upsert)"""
    from apps.incidents.models import Incident
    from .models import StatisticsDaily

    start = timezone.make_aware(
        timezone.datetime.combine(target_date, timezone.datetime.min.time())
    )
    end = start + timedelta(days=1)

    qs = Incident.objects.filter(received_at__gte=start, received_at__lt=end)
    total = qs.count()
    completed = qs.filter(status='completed').count()

    completed_qs = qs.filter(status='completed')
    sla_arrival_ok = completed_qs.filter(sla_arrival_ok=True).count()
    sla_resolve_ok = completed_qs.filter(sla_resolve_ok=True).count()

    # 평균 도착/처리 시간 (분)
    avg_arrival_min = None
    avg_resolve_min = None
    completed_with_times = completed_qs.filter(
        arrived_at__isnull=False, completed_at__isnull=False
    )
    if completed_with_times.exists():
        arrival_mins = []
        resolve_mins = []
        for inc in completed_with_times:
            if inc.arrived_at and inc.received_at:
                arrival_mins.append(
                    (inc.arrived_at - inc.received_at).total_seconds() / 60
                )
            if inc.completed_at and inc.received_at:
                resolve_mins.append(
                    (inc.completed_at - inc.received_at).total_seconds() / 60
                )
        if arrival_mins:
            avg_arrival_min = round(sum(arrival_mins) / len(arrival_mins), 1)
        if resolve_mins:
            avg_resolve_min = round(sum(resolve_mins) / len(resolve_mins), 1)

    StatisticsDaily.objects.update_or_create(
        stat_date=target_date,
        defaults={
            'total_incidents':    total,
            'completed_incidents': completed,
            'sla_arrival_ok':     sla_arrival_ok,
            'sla_resolve_ok':     sla_resolve_ok,
            'avg_arrival_min':    avg_arrival_min,
            'avg_resolve_min':    avg_resolve_min,
        },
    )


# ─────────────────────────────────────────────────────────────
# 2. aggregate_monthly
# ─────────────────────────────────────────────────────────────
def aggregate_monthly(year: int, month: int):
    """연월 기준 월별 통계를 지원청별로 집계해 StatisticsMonthly에 저장(upsert)"""
    from apps.incidents.models import Incident
    from apps.schools.models import SupportCenter
    from .models import StatisticsMonthly

    start = timezone.make_aware(timezone.datetime(year, month, 1))
    if month == 12:
        end = timezone.make_aware(timezone.datetime(year + 1, 1, 1))
    else:
        end = timezone.make_aware(timezone.datetime(year, month + 1, 1))

    base_qs = Incident.objects.filter(received_at__gte=start, received_at__lt=end)

    for center in SupportCenter.objects.all():
        qs = base_qs.filter(school__support_center=center)
        total = qs.count()
        completed = qs.filter(status='completed').count()
        completed_qs = qs.filter(status='completed')

        sla_arrival_ok = completed_qs.filter(sla_arrival_ok=True).count()
        sla_resolve_ok = completed_qs.filter(sla_resolve_ok=True).count()

        sla_arrival_rate = round(sla_arrival_ok / completed * 100, 1) if completed else 0.0
        sla_resolve_rate = round(sla_resolve_ok / completed * 100, 1) if completed else 0.0

        # 평균 도착/처리 시간
        avg_arrival_min = None
        avg_resolve_min = None
        timed_qs = completed_qs.filter(arrived_at__isnull=False, completed_at__isnull=False)
        if timed_qs.exists():
            arrivals = []
            resolves = []
            for inc in timed_qs:
                if inc.arrived_at and inc.received_at:
                    arrivals.append((inc.arrived_at - inc.received_at).total_seconds() / 60)
                if inc.completed_at and inc.received_at:
                    resolves.append((inc.completed_at - inc.received_at).total_seconds() / 60)
            if arrivals:
                avg_arrival_min = round(sum(arrivals) / len(arrivals), 1)
            if resolves:
                avg_resolve_min = round(sum(resolves) / len(resolves), 1)

        StatisticsMonthly.objects.update_or_create(
            year=year, month=month, support_center=center,
            defaults={
                'total_incidents':    total,
                'completed_incidents': completed,
                'sla_arrival_rate':   sla_arrival_rate,
                'sla_resolve_rate':   sla_resolve_rate,
                'avg_arrival_min':    avg_arrival_min,
                'avg_resolve_min':    avg_resolve_min,
            },
        )


# ─────────────────────────────────────────────────────────────
# 3~7. IncidentPatternAnalyzer
# ─────────────────────────────────────────────────────────────
class IncidentPatternAnalyzer:
    """장애 패턴 분석 유틸리티 (정적 메서드 모음)"""

    @staticmethod
    def hourly_distribution(qs) -> list:
        """시간대별(0~23) 장애 발생 건수 반환

        Returns: [{'hour': 0, 'count': N}, ..., {'hour': 23, 'count': N}]
        """
        counts = {h: 0 for h in range(24)}
        for inc in qs.values_list('received_at', flat=True):
            if inc:
                local_dt = timezone.localtime(inc)
                counts[local_dt.hour] += 1
        return [{'hour': h, 'count': counts[h]} for h in range(24)]

    @staticmethod
    def weekday_distribution(qs) -> list:
        """요일별(0=월 ~ 6=일) 장애 발생 건수 반환

        Returns: [{'weekday': 0, 'label': '월', 'count': N}, ...]
        """
        labels = ['월', '화', '수', '목', '금', '토', '일']
        counts = {d: 0 for d in range(7)}
        for inc in qs.values_list('received_at', flat=True):
            if inc:
                local_dt = timezone.localtime(inc)
                counts[local_dt.weekday()] += 1
        return [
            {'weekday': d, 'label': labels[d], 'count': counts[d]}
            for d in range(7)
        ]

    @staticmethod
    def category_trend(year: int, month: int) -> list:
        """해당 연월의 카테고리별 장애 발생 건수 (내림차순)

        Returns: [{'category': '유선망', 'code': 'wired', 'count': N}, ...]
        """
        from apps.incidents.models import Incident

        start = timezone.make_aware(timezone.datetime(year, month, 1))
        if month == 12:
            end = timezone.make_aware(timezone.datetime(year + 1, 1, 1))
        else:
            end = timezone.make_aware(timezone.datetime(year, month + 1, 1))

        rows = (
            Incident.objects
            .filter(received_at__gte=start, received_at__lt=end, category__isnull=False)
            .values('category__name', 'category__code')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        return [
            {'category': r['category__name'], 'code': r['category__code'], 'count': r['count']}
            for r in rows
        ]

    @staticmethod
    def recurrence_hotspots(center, top_n: int = 10) -> list:
        """지원청 내 재발 다발 학교+카테고리 조합 (top_n개)

        Returns: [{'school': '학교명', 'category': '분류명', 'count': N}, ...]
        """
        from apps.incidents.models import Incident

        rows = (
            Incident.objects
            .filter(school__support_center=center, category__isnull=False)
            .values('school__name', 'category__name')
            .annotate(count=Count('id'))
            .filter(count__gte=2)
            .order_by('-count')[:top_n]
        )
        return [
            {
                'school':   r['school__name'],
                'category': r['category__name'],
                'count':    r['count'],
            }
            for r in rows
        ]

    @staticmethod
    def school_risk_score(center, top_n: int = 20) -> list:
        """학교별 위험도 점수 계산 (장애 수 × 우선순위 가중치)

        우선순위 가중치: critical=4, high=3, medium=2, low=1
        Returns: [{'school': '학교명', 'school_id': N, 'risk_score': F, 'total': N}, ...]
        """
        from apps.incidents.models import Incident

        WEIGHTS = {'critical': 4, 'high': 3, 'medium': 2, 'low': 1}

        rows = (
            Incident.objects
            .filter(school__support_center=center)
            .values('school__id', 'school__name', 'priority')
            .annotate(count=Count('id'))
        )

        scores: dict = {}
        for r in rows:
            sid = r['school__id']
            if sid not in scores:
                scores[sid] = {'school': r['school__name'], 'school_id': sid,
                               'risk_score': 0, 'total': 0}
            w = WEIGHTS.get(r['priority'], 1)
            scores[sid]['risk_score'] += w * r['count']
            scores[sid]['total'] += r['count']

        result = sorted(scores.values(), key=lambda x: x['risk_score'], reverse=True)
        return result[:top_n]


# ─────────────────────────────────────────────────────────────
# 8. PerformanceAnalyzer
# ─────────────────────────────────────────────────────────────
class PerformanceAnalyzer:
    """인력 성과 분석"""

    @staticmethod
    def worker_performance(workers, start, end) -> list:
        """인력별 SLA 준수율·처리시간 분석

        Args:
            workers: User queryset
            start, end: datetime (aware)

        Returns: [{'worker': username, 'total_assigned': N,
                   'sla_arrival_rate': F, 'avg_resolve_min': F}, ...]
        """
        from apps.incidents.models import IncidentAssignment

        result = []
        for worker in workers:
            assigns = IncidentAssignment.objects.filter(
                worker=worker,
                incident__received_at__gte=start,
                incident__received_at__lt=end,
            ).select_related('incident')

            total = assigns.count()
            if total == 0:
                result.append({
                    'worker': worker.username,
                    'worker_id': worker.pk,
                    'total_assigned': 0,
                    'sla_arrival_rate': 0.0,
                    'avg_resolve_min': None,
                })
                continue

            sla_ok = assigns.filter(incident__sla_arrival_ok=True).count()
            sla_arrival_rate = round(sla_ok / total * 100, 1)

            resolve_mins = []
            for a in assigns:
                inc = a.incident
                if inc.completed_at and inc.received_at:
                    resolve_mins.append(
                        (inc.completed_at - inc.received_at).total_seconds() / 60
                    )
            avg_resolve_min = round(sum(resolve_mins) / len(resolve_mins), 1) if resolve_mins else None

            result.append({
                'worker': worker.username,
                'worker_id': worker.pk,
                'total_assigned': total,
                'sla_arrival_rate': sla_arrival_rate,
                'avg_resolve_min': avg_resolve_min,
            })

        return result
