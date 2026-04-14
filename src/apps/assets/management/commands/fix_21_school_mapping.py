"""
21대 학교명 매핑 오류 일괄 수정

CSV 등록 시 학교명이 달라 매칭 실패한 장비 → 올바른 학교로 연결 + installed 상태 전환

사용법:
  python manage.py fix_21_school_mapping --dry-run
  python manage.py fix_21_school_mapping
"""
from django.core.management.base import BaseCommand


FIXES = {
    'CEN45EPR0269': '서울전곡초등학교',
    'CEN45EPR0411': '서울전곡초등학교',
    'CEN45EPR0853': '서울전곡초등학교',
    'CEN02EPS0510': '서울백영고등학교',
    'CEN02EPS0836': '서울백영고등학교',
    'CEN02EPS0982': '서울백영고등학교',
    'CEN02EPS2852': '서울백영고등학교',
    'CEN02EPS2853': '서울백영고등학교',
    'CEN02EPS3520': '서울백영고등학교',
    'CEN03EPS3105': '서울백영고등학교',
    'CEN03EPS3106': '서울백영고등학교',
    'CEN03EPS3139': '서울백영고등학교',
    'CEN03EPS3255': '서울백영고등학교',
    'CEN03EPS4063': '서울백영고등학교',
    'CEN03EPS4222': '서울백영고등학교',
    'CEN03EPS4226': '서울백영고등학교',
    'A180124AR0100021': '잠실여자중학교',
    'A180124AR0100057': '잠실여자중학교',
    'A180124AR0100058': '잠실여자중학교',
    'A180124AR0100059': '잠실여자중학교',
    'A180124AR0100060': '잠실여자중학교',
}


class Command(BaseCommand):
    help = '21대 학교명 매핑 오류 수정 — warehouse → installed + 올바른 학교 연결'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='DB 변경 없이 결과만 출력')

    def handle(self, *args, **options):
        from apps.assets.models import Asset
        from apps.schools.models import School

        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('** DRY-RUN **\n'))

        school_cache = {}
        updated = not_found = 0

        for sn, school_name in FIXES.items():
            if school_name not in school_cache:
                school_cache[school_name] = School.objects.filter(name=school_name).first()
            school = school_cache[school_name]
            if not school:
                self.stdout.write(self.style.ERROR(f'  학교 미존재: {school_name}'))
                continue

            try:
                asset = Asset.objects.get(serial_number=sn)
            except Asset.DoesNotExist:
                self.stdout.write(f'  [미존재] {sn}')
                not_found += 1
                continue

            self.stdout.write(
                f'  {sn}: {asset.get_status_display()} → 학교 설치 | {school_name}'
            )
            if not dry_run:
                asset.status = 'installed'
                asset.current_school = school
                asset.current_center = school.support_center
                asset.save(update_fields=['status', 'current_school', 'current_center'])
            updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'\n완료 — 수정: {updated}건, DB미존재: {not_found}건'
        ))
