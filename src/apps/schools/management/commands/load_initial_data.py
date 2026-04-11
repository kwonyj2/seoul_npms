"""
초기 데이터 로드 커맨드
Usage: python manage.py load_initial_data
"""
from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = '지원청, 학제, 장애분류 초기 데이터 로드'

    def handle(self, *args, **options):
        self.stdout.write('초기 데이터 로드 시작...')
        try:
            call_command('loaddata', 'apps/schools/fixtures/initial_data.json', verbosity=1)
            self.stdout.write(self.style.SUCCESS('✓ 지원청/학제 데이터 로드 완료'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'지원청/학제: {e}'))

        try:
            call_command('loaddata', 'apps/incidents/fixtures/initial_data.json', verbosity=1)
            self.stdout.write(self.style.SUCCESS('✓ 장애분류/SLA 데이터 로드 완료'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'장애분류/SLA: {e}'))

        self.stdout.write(self.style.SUCCESS('초기 데이터 로드 완료!'))
