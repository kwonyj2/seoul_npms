"""
학교정보.xlsx → DB 등록 관리 명령어

사용법:
  python manage.py load_schools
  python manage.py load_schools --file /path/to/학교정보.xlsx
  python manage.py load_schools --update   # 기존 데이터도 업데이트
  python manage.py load_schools --dry-run  # 실제 저장 없이 미리보기
"""
import os
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


# ── 매핑 테이블 ────────────────────────────────────────────────

SUPPORT_CENTER_MAP = {
    '동부':    ('dongbu',    '동부교육지원청'),
    '서부':    ('seobu',     '서부교육지원청'),
    '남부':    ('nambu',     '남부교육지원청'),
    '북부':    ('bukbu',     '북부교육지원청'),
    '중부':    ('jungbu',    '중부교육지원청'),
    '강동송파': ('gangdong',  '강동송파교육지원청'),
    '강서양천': ('gangseo',   '강서양천교육지원청'),
    '강남서초': ('gangnam',   '강남서초교육지원청'),
    '동작관악': ('dongjak',   '동작관악교육지원청'),
    '성동광진': ('seongdong', '성동광진교육지원청'),
    '성북강북': ('seongbuk',  '성북강북교육지원청'),
}

SCHOOL_TYPE_MAP = {
    '유치원':    ('kindergarten', 1),
    '초등학교':   ('elementary',   2),
    '중학교':    ('middle',       3),
    '고등학교':   ('high',         4),
    '특수학교':   ('special',      5),
    '고등기술학교': ('vocational',  6),
    '각종학교':   ('etc',          7),
}

# 엑셀 컬럼 인덱스 (0-based)
COL = {
    'center':   2,   # 교육지원청
    'name':     4,   # 학교명
    'type':     5,   # 학제
    'code':     11,  # 학교코드
    'zip_code': 12,  # 우편번호
    'address':  13,  # 주소
    'phone':    14,  # 전화번호
    'fax':      15,  # 팩스번호
    'homepage': 16,  # 홈페이지
    'lat':      17,  # 위도
    'lng':      18,  # 경도
}


class Command(BaseCommand):
    help = '학교정보.xlsx 파일을 읽어 DB에 학교 정보를 등록합니다.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            default=None,
            help='엑셀 파일 경로 (기본: media/data/학교정보.xlsx)',
        )
        parser.add_argument(
            '--update',
            action='store_true',
            help='이미 존재하는 학교 정보도 업데이트',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            help='실제 저장 없이 결과만 출력',
        )

    def handle(self, *args, **options):
        try:
            import openpyxl
        except ImportError:
            raise CommandError('openpyxl이 설치되어 있지 않습니다. pip install openpyxl')

        from apps.schools.models import SupportCenter, SchoolType, School

        # 파일 경로 결정
        file_path = options['file']
        if not file_path:
            from django.conf import settings
            nas_root = getattr(settings, 'NAS_MEDIA_ROOT', None)
            candidates = []
            if nas_root:
                candidates.append(os.path.join(nas_root, 'data', '학교정보.xlsx'))
            candidates.append(os.path.join(settings.BASE_DIR, 'media', 'data', '학교정보.xlsx'))
            file_path = next((p for p in candidates if os.path.exists(p)), candidates[0])

        if not os.path.exists(file_path):
            raise CommandError(f'파일을 찾을 수 없습니다: {file_path}')

        do_update = options['update']
        dry_run   = options['dry_run']

        self.stdout.write(f'파일: {file_path}')
        if dry_run:
            self.stdout.write(self.style.WARNING('** DRY-RUN 모드 — DB에 저장하지 않습니다 **'))

        # ── 1. SupportCenter 준비 ────────────────────────────────
        self.stdout.write('\n[1] 교육지원청 등록...')
        center_objects = {}
        for label, (code, full_name) in SUPPORT_CENTER_MAP.items():
            if not dry_run:
                obj, created = SupportCenter.objects.get_or_create(
                    code=code,
                    defaults={'name': full_name}
                )
                if created:
                    self.stdout.write(f'  ✓ 생성: {full_name}')
            else:
                obj = type('SC', (), {'id': f'[DRY:{code}]', 'name': full_name})()
            center_objects[label] = obj
        self.stdout.write(self.style.SUCCESS(f'  교육지원청 {len(center_objects)}개 준비'))

        # ── 2. SchoolType 준비 ───────────────────────────────────
        self.stdout.write('\n[2] 학제 등록...')
        type_objects = {}
        for label, (code, order) in SCHOOL_TYPE_MAP.items():
            if not dry_run:
                obj, created = SchoolType.objects.get_or_create(
                    code=code,
                    defaults={'name': label, 'order': order}
                )
                if created:
                    self.stdout.write(f'  ✓ 생성: {label}')
            else:
                obj = type('ST', (), {'id': f'[DRY:{code}]', 'name': label})()
            type_objects[label] = obj
        self.stdout.write(self.style.SUCCESS(f'  학제 {len(type_objects)}개 준비'))

        # ── 3. 엑셀 파일 읽기 ────────────────────────────────────
        self.stdout.write('\n[3] 엑셀 파일 읽는 중...')
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        data_rows = rows[1:]  # 헤더 제외
        self.stdout.write(f'  데이터 행 수: {len(data_rows)}')

        # ── 4. 학교 등록 ─────────────────────────────────────────
        self.stdout.write('\n[4] 학교 등록 중...')
        created_cnt = updated_cnt = skipped_cnt = error_cnt = 0

        with transaction.atomic():
            for i, row in enumerate(data_rows, start=2):
                if not any(row):
                    continue

                def cell(col_key):
                    val = row[COL[col_key]]
                    if val is None:
                        return ''
                    return str(val).strip()

                school_name   = cell('name')
                center_label  = cell('center')
                type_label    = cell('type')

                if not school_name:
                    continue

                # 알 수 없는 지원청/학제 처리
                if center_label not in center_objects:
                    self.stderr.write(f'  [행 {i}] 알 수 없는 지원청: "{center_label}" ({school_name}) — 건너뜀')
                    error_cnt += 1
                    continue
                if type_label not in type_objects:
                    self.stderr.write(f'  [행 {i}] 알 수 없는 학제: "{type_label}" ({school_name}) — 건너뜀')
                    error_cnt += 1
                    continue

                center_obj = center_objects[center_label]
                type_obj   = type_objects[type_label]

                # lat/lng 변환
                try:
                    lat = float(row[COL['lat']]) if row[COL['lat']] else None
                except (TypeError, ValueError):
                    lat = None
                try:
                    lng = float(row[COL['lng']]) if row[COL['lng']] else None
                except (TypeError, ValueError):
                    lng = None

                # homepage URL 정제
                homepage = cell('homepage')
                if homepage and not homepage.startswith('http'):
                    homepage = 'http://' + homepage

                school_defaults = {
                    'school_type': type_obj,
                    'code':        cell('code'),
                    'zip_code':    cell('zip_code'),
                    'address':     cell('address'),
                    'phone':       cell('phone'),
                    'fax':         cell('fax'),
                    'homepage':    homepage,
                    'lat':         lat,
                    'lng':         lng,
                    'is_active':   True,
                }

                if dry_run:
                    self.stdout.write(
                        f'  [DRY] {center_label} | {type_label} | {school_name} | {cell("address")[:30]}'
                    )
                    created_cnt += 1
                    continue

                try:
                    existing = School.objects.filter(
                        support_center=center_obj,
                        name=school_name,
                    ).first()

                    if existing:
                        if do_update:
                            for k, v in school_defaults.items():
                                setattr(existing, k, v)
                            existing.save()
                            updated_cnt += 1
                        else:
                            skipped_cnt += 1
                    else:
                        School.objects.create(
                            support_center=center_obj,
                            name=school_name,
                            **school_defaults,
                        )
                        created_cnt += 1
                except Exception as exc:
                    self.stderr.write(f'  [행 {i}] 오류: {school_name} — {exc}')
                    error_cnt += 1

            if dry_run:
                transaction.set_rollback(True)

        # ── 5. 결과 출력 ─────────────────────────────────────────
        self.stdout.write('\n' + '─' * 50)
        self.stdout.write(self.style.SUCCESS(f'  신규 등록: {created_cnt}개'))
        if do_update:
            self.stdout.write(self.style.SUCCESS(f'  업데이트:  {updated_cnt}개'))
        else:
            self.stdout.write(f'  이미 존재: {skipped_cnt}개 (--update 옵션으로 업데이트 가능)')
        if error_cnt:
            self.stdout.write(self.style.WARNING(f'  오류:      {error_cnt}개'))
        if dry_run:
            self.stdout.write(self.style.WARNING('** DRY-RUN — 실제 저장 없음 **'))
        else:
            total = School.objects.count()
            self.stdout.write(self.style.SUCCESS(f'\nDB 학교 총 {total}개'))
