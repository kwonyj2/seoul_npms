"""
Celery Beat 주기 태스크 DB 등록 커맨드
Usage: python manage.py setup_celery_beat
"""
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Celery Beat 주기 태스크를 DB에 등록'

    def handle(self, *args, **options):
        from django_celery_beat.models import PeriodicTask, IntervalSchedule, CrontabSchedule

        self.stdout.write('Celery Beat 태스크 등록 시작...')

        # ── 인터벌 스케줄 생성 ─────────────────────────────────────────
        every_5min, _  = IntervalSchedule.objects.get_or_create(every=5,  period=IntervalSchedule.MINUTES)
        every_30min, _ = IntervalSchedule.objects.get_or_create(every=30, period=IntervalSchedule.MINUTES)

        # ── Crontab 스케줄 생성 ────────────────────────────────────────
        # 매일 자정 (통계 업데이트)
        daily_midnight, _ = CrontabSchedule.objects.get_or_create(
            minute='0', hour='0', day_of_week='*', day_of_month='*', month_of_year='*',
            timezone='Asia/Seoul'
        )
        # 매월 1일 01:00 (월간 통계)
        monthly_1st, _ = CrontabSchedule.objects.get_or_create(
            minute='0', hour='1', day_of_week='*', day_of_month='1', month_of_year='*',
            timezone='Asia/Seoul'
        )

        tasks = [
            {
                'name':       'SNMP 네트워크 장비 폴링 (30분)',
                'task':       'apps.network.tasks.poll_snmp_devices',
                'schedule':   every_30min,
                'schedule_key': 'interval',
                'enabled':    True,
            },
            {
                'name':       '일별 통계 업데이트 (자정)',
                'task':       'apps.statistics.tasks.update_daily_statistics',
                'schedule':   daily_midnight,
                'schedule_key': 'crontab',
                'enabled':    True,
            },
            {
                'name':       '월별 통계 업데이트 (매월 1일)',
                'task':       'apps.statistics.tasks.update_monthly_statistics',
                'schedule':   monthly_1st,
                'schedule_key': 'crontab',
                'enabled':    True,
            },
            {
                'name':       '세션 정리 (5분)',
                'task':       'apps.accounts.tasks.cleanup_sessions',
                'schedule':   every_5min,
                'schedule_key': 'interval',
                'enabled':    True,
            },
        ]

        created, updated = 0, 0
        for t in tasks:
            defaults = {
                'enabled':    t['enabled'],
                'start_time': timezone.now(),
            }
            if t['schedule_key'] == 'interval':
                defaults['interval']  = t['schedule']
                defaults['crontab']   = None
            else:
                defaults['crontab']   = t['schedule']
                defaults['interval']  = None

            obj, is_new = PeriodicTask.objects.update_or_create(
                name=t['name'],
                task=t['task'],
                defaults=defaults,
            )
            if is_new:
                created += 1
                self.stdout.write(self.style.SUCCESS(f'  ✓ 등록: {t["name"]}'))
            else:
                updated += 1
                self.stdout.write(f'  ~ 갱신: {t["name"]}')

        self.stdout.write(self.style.SUCCESS(
            f'\nCelery Beat 태스크 등록 완료 — 신규 {created}개 / 갱신 {updated}개'
        ))
