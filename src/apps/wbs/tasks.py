"""WBS Celery 태스크"""
from datetime import date, timedelta
from celery import shared_task
import logging

logger = logging.getLogger('apps')


@shared_task(name='apps.wbs.tasks.snapshot_wbs_progress')
def snapshot_wbs_progress():
    """WBS 전체 항목의 주간 진척 스냅샷 저장 — 매주 월요일 자동 실행"""
    from apps.wbs.models import WBSItem, WBSProgressHistory

    today = date.today()
    # 이번 주 월요일 기준
    week_start = today - timedelta(days=today.weekday())

    items = WBSItem.objects.exclude(progress_source='children').select_related('project')
    created = 0

    for item in items:
        # 계획 진척률 계산
        planned_pct = 0.0
        if item.planned_end and item.planned_end <= today:
            planned_pct = 100.0
        elif item.planned_start and item.planned_start <= today and item.planned_end:
            elapsed = (today - item.planned_start).days
            total = (item.planned_end - item.planned_start).days or 1
            planned_pct = min(elapsed / total * 100, 100)

        _, is_new = WBSProgressHistory.objects.update_or_create(
            item=item, week_date=week_start,
            defaults={
                'progress': item.progress,
                'planned_progress': round(planned_pct, 1),
            }
        )
        if is_new:
            created += 1

    logger.info('WBS 진척 스냅샷 완료: %d건 기록', created)
    return {'created': created, 'total': items.count()}
