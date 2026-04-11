"""
스위치(예비장비) 관리 목록.xlsx 기준으로 Asset 상태를 일괄 업데이트

위치 컬럼 → status 매핑:
  학교    → installed  (current_school 연결)
  창고1   → warehouse
  창고2   → warehouse
  지원청  → center     (current_center 연결)
  기타    → warehouse

사용법:
  python manage.py fix_asset_status
  python manage.py fix_asset_status --file /path/to/파일.xlsx
  python manage.py fix_asset_status --dry-run
"""
import os
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = '스위치(예비장비) 관리 목록.xlsx 기준 Asset 상태 일괄 업데이트'

    def add_arguments(self, parser):
        parser.add_argument('--file',    default=None, help='Excel 파일 경로')
        parser.add_argument('--dry-run', action='store_true', dest='dry_run', help='DB 변경 없이 결과만 출력')

    def handle(self, *args, **options):
        try:
            import openpyxl
        except ImportError:
            raise CommandError('openpyxl 미설치')

        from apps.assets.models import Asset
        from apps.schools.models import School, SupportCenter

        file_path = options['file'] or '/mnt/d/감리/스위치(예비장비) 관리 목록.xlsx'
        if not os.path.exists(file_path):
            raise CommandError(f'파일 없음: {file_path}')

        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('** DRY-RUN — DB 변경 없음 **'))

        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb['스위치 관리 내역']
        rows = list(ws.iter_rows(values_only=True))
        self.stdout.write(f'파일: {file_path}  ({len(rows) - 1:,}행)')

        # 캐시
        school_cache = {s.name: s for s in School.objects.all()}
        center_cache = {c.name: c for c in SupportCenter.objects.all()}
        # 단축명 ('동부' → 동부교육지원청) 매핑
        for c in SupportCenter.objects.all():
            short = c.name.replace('교육지원청', '').strip()
            if short:
                center_cache.setdefault(short, c)

        # 컬럼 인덱스 (헤더: 연번,No.,사업,모델,제조번호,교육지원청,학교,학교분류,설치일,위치)
        # index:       0    1   2   3    4      5       6    7       8    9
        COL_SN      = 4
        COL_DIST    = 5
        COL_SCHOOL  = 6
        COL_LOC     = 9

        def loc_to_status(loc):
            if loc == '학교':
                return 'installed'
            if loc == '지원청':
                return 'edu_office'   # 교육지원청 설치 (센터 보관과 구분)
            return 'warehouse'  # 창고1, 창고2, 기타

        updated = skipped = not_found = 0
        status_counts = {'installed': 0, 'edu_office': 0, 'warehouse': 0}

        with transaction.atomic():
            for row in rows[1:]:
                sn       = str(row[COL_SN]).strip()  if row[COL_SN]     else ''
                district = str(row[COL_DIST]).strip() if row[COL_DIST]   else ''
                school_n = str(row[COL_SCHOOL]).strip() if row[COL_SCHOOL] else ''
                loc      = str(row[COL_LOC]).strip()  if row[COL_LOC]    else ''

                if not sn:
                    continue

                new_status = loc_to_status(loc)
                school  = school_cache.get(school_n) if new_status == 'installed' else None
                center  = center_cache.get(district) if district else None

                try:
                    asset = Asset.objects.get(serial_number=sn)
                except Asset.DoesNotExist:
                    not_found += 1
                    if dry_run:
                        self.stdout.write(f'  [미존재] {sn}')
                    continue

                # 변경 필요 여부 확인
                needs_update = (
                    asset.status        != new_status or
                    asset.current_school != school    or
                    asset.current_center != center
                )
                if not needs_update:
                    skipped += 1
                    continue

                if dry_run:
                    self.stdout.write(
                        f'  {sn}: {asset.status} → {new_status}'
                        f' | 학교={school_n or "-"}'
                        f' | 지원청={district or "-"}'
                    )
                else:
                    asset.status         = new_status
                    asset.current_school = school
                    asset.current_center = center
                    asset.save(update_fields=['status', 'current_school', 'current_center'])

                updated += 1
                status_counts[new_status] += 1

            if dry_run:
                raise transaction.TransactionManagementError('dry-run rollback')

        self.stdout.write(self.style.SUCCESS(
            f'\n완료 — 업데이트: {updated:,}개 / 변경없음: {skipped:,}개 / DB미존재: {not_found:,}개'
        ))
        self.stdout.write(
            f'  → installed(학교): {status_counts["installed"]:,}  '
            f'edu_office(교육지원청): {status_counts["edu_office"]:,}  '
            f'warehouse(창고): {status_counts["warehouse"]:,}'
        )
