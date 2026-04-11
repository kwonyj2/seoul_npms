"""
show_logs — 로그 파일 최근 N줄 출력 관리 커맨드

사용법:
  python manage.py show_logs               # 전체 목록
  python manage.py show_logs app           # app.log 마지막 50줄
  python manage.py show_logs error -n 100  # error.log 마지막 100줄
  python manage.py show_logs celery -n 20  # celery.log 마지막 20줄
"""
import os
from collections import deque
from django.core.management.base import BaseCommand, CommandError

LOG_DIR = '/app/logs'

LOG_FILES = {
    'app':       'app.log',
    'access':    'access.log',
    'error':     'error.log',
    'security':  'security.log',
    'celery':    'celery.log',
}


class Command(BaseCommand):
    help = '로그 파일 최근 N줄 출력'

    def add_arguments(self, parser):
        parser.add_argument(
            'log_name',
            nargs='?',
            default=None,
            choices=list(LOG_FILES.keys()),
            help=f'로그 종류: {", ".join(LOG_FILES.keys())} (생략 시 목록 출력)',
        )
        parser.add_argument(
            '-n', '--lines',
            type=int,
            default=50,
            help='출력할 줄 수 (기본 50)',
        )

    def handle(self, *args, **options):
        log_name = options['log_name']

        if log_name is None:
            self._list_files()
            return

        filename = LOG_FILES[log_name]
        filepath = os.path.join(LOG_DIR, filename)

        if not os.path.exists(filepath):
            self.stdout.write(
                self.style.WARNING(f'[{filename}] 파일 없음 (아직 로그 기록 없음)')
            )
            return

        n = options['lines']
        lines = self._tail(filepath, n)

        self.stdout.write(self.style.SUCCESS(
            f'\n── {filename} (최근 {n}줄) ──────────────────────'
        ))
        for line in lines:
            txt = line.rstrip()
            if ' ERROR ' in txt or ' CRITICAL ' in txt:
                self.stdout.write(self.style.ERROR(txt))
            elif ' WARNING ' in txt:
                self.stdout.write(self.style.WARNING(txt))
            else:
                self.stdout.write(txt)

    def _list_files(self):
        self.stdout.write(self.style.SUCCESS('\n── NPMS 로그 파일 현황 ──────────────────────'))
        for key, filename in LOG_FILES.items():
            filepath = os.path.join(LOG_DIR, filename)
            if os.path.exists(filepath):
                size = os.path.getsize(filepath)
                size_str = f'{size/1024:.1f} KB' if size < 1024*1024 else f'{size/1024/1024:.1f} MB'
                self.stdout.write(f'  {key:<10} {filename:<20} {size_str:>10}')
            else:
                self.stdout.write(
                    self.style.WARNING(f'  {key:<10} {filename:<20} {"(없음)":>10}')
                )
        self.stdout.write(
            '\n사용법: python manage.py show_logs <종류> [-n <줄수>]\n'
        )

    @staticmethod
    def _tail(filepath, n):
        with open(filepath, encoding='utf-8', errors='replace') as f:
            return list(deque(f, maxlen=n))
