"""
정기점검.xlsx → progress.InspectionPlan + SchoolInspection 임포트

컬럼 (자동 감지):
  연번, 권역, 교육지원청, 행정구, 학교명, 학제

사용법:
  python manage.py import_inspection
  python manage.py import_inspection --file /path/to/2026년\ 2분기\ 정기점검.xlsx
  python manage.py import_inspection --plan-name "2026년 2분기 정기점검" --year 2026 --quarter 2
  python manage.py import_inspection --dry-run
"""
import os
from datetime import date
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

# 차수별 기본 기간 (사업 확정 후 변경 가능)
ROUND_DATES = {
    1: (date(2000, 7, 1),  date(2000, 8, 31)),
    2: (date(2000, 9, 1),  date(2000, 10, 31)),
    3: (date(2000, 11, 1), date(2000, 11, 30)),
}


class Command(BaseCommand):
    help = '정기점검.xlsx 를 읽어 InspectionPlan + SchoolInspection 에 등록합니다.'

    def add_arguments(self, parser):
        parser.add_argument('--file',       default=None)
        parser.add_argument('--plan-name',  default=None, dest='plan_name')
        parser.add_argument('--year',       type=int, default=None)
        parser.add_argument('--quarter',    type=int, default=None, choices=[1, 2, 3],
                            help='차수 (1차/2차/3차)')
        parser.add_argument('--start-date', default=None, dest='start_date',
                            help='YYYY-MM-DD (기본: 차수별 시작일)')
        parser.add_argument('--end-date',   default=None, dest='end_date',
                            help='YYYY-MM-DD (기본: 차수별 종료일)')
        parser.add_argument('--plan-type',  default='regular', dest='plan_type',
                            choices=['regular', 'special', 'quarterly', 'project', 'survey', 'followup'])
        parser.add_argument('--update',     action='store_true')
        parser.add_argument('--dry-run',    action='store_true', dest='dry_run')

    def handle(self, *args, **options):
        try:
            import openpyxl
        except ImportError:
            raise CommandError('openpyxl 미설치.')

        from apps.progress.models import InspectionPlan, SchoolInspection
        from apps.schools.models import School

        # ── 파일 경로 ──────────────────────────────────────────────
        file_path = options['file']
        if not file_path:
            from django.conf import settings
            file_path = os.path.join(settings.BASE_DIR, 'media', 'data', '정기점검.xlsx')
            if not os.path.exists(file_path):
                # 연도·차수로 자동 탐색
                year    = options['year']    or date.today().year
                quarter = options['quarter'] or 1
                candidates = [
                    f'{year}년 {quarter}차 정기점검.xlsx',
                    f'{year}년_{quarter}차_정기점검.xlsx',
                    f'{year}년 {quarter}분기 정기점검.xlsx',
                    f'{year}년_{quarter}분기_정기점검.xlsx',
                ]
                base = '/home/kwonyj/network_pms/src/nas/media/npms/data'
                for c in candidates:
                    p = os.path.join(base, c)
                    if os.path.exists(p):
                        file_path = p
                        break

        if not file_path or not os.path.exists(file_path):
            raise CommandError(f'파일 없음: {file_path}')

        # ── 계획 메타 정보 ─────────────────────────────────────────
        year    = options['year']
        quarter = options['quarter']

        # 파일명에서 연도·차수 추출 시도
        if not year or not quarter:
            import re
            fname = os.path.basename(file_path)
            m = re.search(r'(\d{4})년\s*(\d)(?:차|분기)', fname)
            if m:
                year    = year    or int(m.group(1))
                quarter = quarter or int(m.group(2))

        year    = year    or date.today().year
        quarter = quarter or 1

        plan_name = options['plan_name'] or f'{year}년 {quarter}차 정기점검'

        # 날짜 계산
        q_start, q_end = ROUND_DATES.get(quarter, (date(year, 1, 1), date(year, 12, 31)))
        start_date = (
            date.fromisoformat(options['start_date']) if options['start_date']
            else q_start.replace(year=year)
        )
        end_date = (
            date.fromisoformat(options['end_date']) if options['end_date']
            else q_end.replace(year=year)
        )

        dry_run   = options['dry_run']
        do_update = options['update']
        plan_type = options['plan_type']

        self.stdout.write(f'파일: {file_path}')
        self.stdout.write(f'계획: [{plan_name}]  {start_date} ~ {end_date}')
        if dry_run:
            self.stdout.write(self.style.WARNING('** DRY-RUN **'))

        # ── Excel 파싱 ─────────────────────────────────────────────
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            self.stdout.write('데이터 없음')
            return

        headers = [str(h).strip() if h else '' for h in rows[0]]
        self.stdout.write(f'헤더: {headers}')

        def idx(*names):
            for n in names:
                try:
                    return headers.index(n)
                except ValueError:
                    pass
            return None

        COL = {
            'school_name': idx('학교명', '학교', 'school'),
            'district':    idx('교육지원청', '지원청', 'district'),
            'region':      idx('권역', 'region'),
            'gu':          idx('행정구', '구'),
            'school_type': idx('학제', '학교유형', 'type'),
        }
        self.stdout.write(f'컬럼 매핑: {COL}')

        def get(row, key):
            i = COL.get(key)
            if i is None or i >= len(row):
                return ''
            v = row[i]
            return str(v).strip() if v is not None else ''

        # ── School 캐시 ────────────────────────────────────────────
        school_cache = {s.name: s for s in School.objects.all()}

        # ── 실행 ──────────────────────────────────────────────────
        created = updated = skipped = error = not_found = 0

        with transaction.atomic():
            # InspectionPlan 생성/조회
            if dry_run:
                plan = None
                self.stdout.write(f'[DRY] 계획 생성: {plan_name}')
            else:
                plan, plan_created = InspectionPlan.objects.get_or_create(
                    name=plan_name,
                    defaults={
                        'plan_type':  plan_type,
                        'year':       year,
                        'quarter':    quarter,
                        'start_date': start_date,
                        'end_date':   end_date,
                        'status':     'draft',
                    }
                )
                if plan_created:
                    self.stdout.write(self.style.SUCCESS(f'계획 생성: {plan_name} (id={plan.pk})'))
                else:
                    self.stdout.write(f'계획 기존: {plan_name} (id={plan.pk})')

            for row_num, row in enumerate(rows[1:], start=2):
                if not any(row):
                    continue

                school_name = get(row, 'school_name')
                if not school_name:
                    continue

                school = school_cache.get(school_name)
                if not school:
                    # 부분 이름 탐색
                    for name, obj in school_cache.items():
                        if school_name in name or name in school_name:
                            school = obj
                            break

                if not school:
                    self.stdout.write(self.style.WARNING(
                        f'  [행{row_num}] 학교 없음: {school_name}'
                    ))
                    not_found += 1
                    continue

                if dry_run:
                    self.stdout.write(
                        f'  [행{row_num}] {school_name} → {school.name}'
                    )
                    created += 1
                    continue

                try:
                    si, si_created = SchoolInspection.objects.get_or_create(
                        plan=plan,
                        school=school,
                        defaults={'status': 'pending', 'priority': 'normal'},
                    )
                    if si_created:
                        created += 1
                    elif do_update:
                        si.status = 'pending'
                        si.save()
                        updated += 1
                    else:
                        skipped += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'  [행{row_num}] 오류: {e}'))
                    error += 1

        self.stdout.write(self.style.SUCCESS(
            f'\n완료 — 생성: {created}건 / 업데이트: {updated}건 / 스킵: {skipped}건 '
            f'/ 학교미매칭: {not_found}건 / 오류: {error}건'
        ))
