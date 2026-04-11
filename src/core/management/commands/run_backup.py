"""
run_backup — DB 즉시 수동 백업 관리 커맨드

사용법:
  python manage.py run_backup
"""
from django.core.management.base import BaseCommand
from django.conf import settings


class Command(BaseCommand):
    help = 'PostgreSQL DB 즉시 백업 실행'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dir',
            default=None,
            help='백업 저장 디렉토리 (기본: DB_BACKUP_DIR 설정값)',
        )

    def handle(self, *args, **options):
        from core.tasks import _run_pg_dump, _cleanup_old_backups

        backup_dir = options['dir'] or getattr(
            settings, 'DB_BACKUP_DIR', '/home/kwonyj/network_pms/backups'
        )
        keep_days = getattr(settings, 'DB_BACKUP_KEEP_DAYS', 30)

        self.stdout.write(f'백업 시작: {backup_dir}')
        result = _run_pg_dump(backup_dir)

        if result['status'] == 'ok':
            deleted = _cleanup_old_backups(backup_dir, keep_days)
            self.stdout.write(self.style.SUCCESS(
                f'백업 완료: {result["file"]} ({result["size"]})'
            ))
            if deleted:
                self.stdout.write(f'구 백업 {deleted}개 삭제 ({keep_days}일 이상)')
        elif result['status'] == 'timeout':
            self.stdout.write(self.style.ERROR('백업 타임아웃 (5분 초과)'))
        else:
            self.stdout.write(self.style.ERROR(
                f'백업 실패: {result.get("msg", "")}'
            ))
