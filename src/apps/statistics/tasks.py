from config.celery import app as celery_app
import logging

logger = logging.getLogger(__name__)


@celery_app.task
def update_daily_statistics(date_str=None):
    """일별 통계 계산 및 갱신"""
    from django.utils import timezone
    from django.db.models import Avg, Count, Q
    from datetime import date, datetime
    from apps.incidents.models import Incident, IncidentAssignment
    from apps.accounts.models import User
    from .models import StatisticsDaily

    if date_str:
        stat_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    else:
        stat_date = timezone.localdate()

    incidents = Incident.objects.filter(created_at__date=stat_date)
    total    = incidents.count()
    completed = incidents.filter(status='completed').count()

    # SLA 준수 계산
    from .models import SLARecord
    sla_qs = SLARecord.objects.filter(created_at__date=stat_date)
    arr_ok = sla_qs.filter(arrival_ok=True).count()
    res_ok = sla_qs.filter(resolve_ok=True).count()
    avgs   = sla_qs.aggregate(a=Avg('arrival_actual_min'), r=Avg('resolve_actual_min'))

    # 활동 인력 수 (오늘 배정된 인력)
    active_workers = IncidentAssignment.objects.filter(
        assigned_at__date=stat_date
    ).values('worker').distinct().count()

    StatisticsDaily.objects.update_or_create(
        stat_date=stat_date,
        defaults={
            'total_incidents':     total,
            'completed_incidents': completed,
            'sla_arrival_ok':      arr_ok,
            'sla_resolve_ok':      res_ok,
            'avg_arrival_min':     avgs['a'],
            'avg_resolve_min':     avgs['r'],
            'active_workers':      active_workers,
        }
    )
    logger.info(f'Daily statistics updated for {stat_date}: total={total}, completed={completed}')


@celery_app.task
def update_monthly_statistics(year=None, month=None):
    """월별 통계 계산 및 갱신"""
    from django.utils import timezone
    from django.db.models import Avg, Count
    from apps.incidents.models import Incident
    from apps.schools.models import SupportCenter
    from .models import StatisticsMonthly, SatisfactionSurvey

    now = timezone.now()
    year  = year or now.year
    month = month or now.month

    incidents = Incident.objects.filter(
        created_at__year=year, created_at__month=month
    )

    # 전체 월별 통계
    from .models import SLARecord
    sla_all = SLARecord.objects.filter(
        created_at__year=year, created_at__month=month
    )
    total   = incidents.count()
    comp    = incidents.filter(status='completed').count()
    arr_cnt = sla_all.filter(arrival_ok=True).count()
    res_cnt = sla_all.filter(resolve_ok=True).count()
    avgs    = sla_all.aggregate(a=Avg('arrival_actual_min'), r=Avg('resolve_actual_min'))

    # 만족도
    avg_sat = SatisfactionSurvey.objects.filter(
        sent_at__year=year, sent_at__month=month, status='responded'
    ).aggregate(a=Avg('score'))['a']

    StatisticsMonthly.objects.update_or_create(
        year=year, month=month, support_center=None,
        defaults={
            'total_incidents':    total,
            'completed_incidents': comp,
            'sla_arrival_rate':   round(arr_cnt / total * 100, 1) if total else 0,
            'sla_resolve_rate':   round(res_cnt / total * 100, 1) if total else 0,
            'avg_arrival_min':    avgs['a'],
            'avg_resolve_min':    avgs['r'],
            'avg_satisfaction':   avg_sat,
        }
    )

    # 지원청별 월별 통계
    centers = SupportCenter.objects.all()
    for center in centers:
        center_incidents = incidents.filter(school__support_center=center)
        c_total = center_incidents.count()
        c_comp  = center_incidents.filter(status='completed').count()
        c_sla   = SLARecord.objects.filter(
            created_at__year=year, created_at__month=month,
            incident__school__support_center=center
        )
        c_arr = c_sla.filter(arrival_ok=True).count()
        c_res = c_sla.filter(resolve_ok=True).count()
        c_avgs = c_sla.aggregate(a=Avg('arrival_actual_min'), r=Avg('resolve_actual_min'))
        StatisticsMonthly.objects.update_or_create(
            year=year, month=month, support_center=center,
            defaults={
                'total_incidents':    c_total,
                'completed_incidents': c_comp,
                'sla_arrival_rate':   round(c_arr / c_total * 100, 1) if c_total else 0,
                'sla_resolve_rate':   round(c_res / c_total * 100, 1) if c_total else 0,
                'avg_arrival_min':    c_avgs['a'],
                'avg_resolve_min':    c_avgs['r'],
            }
        )
    logger.info(f'Monthly statistics updated for {year}-{month:02d}')
