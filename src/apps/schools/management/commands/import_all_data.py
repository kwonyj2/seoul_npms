"""
운용서버 배포 시 기초 DB 일괄 임포트

지정 폴더에 아래 파일들을 놓으면 순서대로 자동 임포트합니다.

  [필수 파일]
  학교정보.xlsx       → schools, support_centers, school_types
  선생님정보.xlsx     → school_contacts
  인력.xlsx          → accounts (인력/사용자)
  자재내역.xlsx       → materials, warehouse_inventory
  장비목록.xlsm       → school_equipment  (building/floor 분리 포함)
  장비목록.xlsx       → assets (장비 자산관리)

  [선택 파일 — 있을 경우만 처리]
  정기점검.xlsx       → progress (InspectionPlan + SchoolInspection)

기본 데이터 폴더 (--data-dir 미지정 시):
  운용서버: /app/nas/media/npms/data/
  개발환경: <BASE_DIR>/media/data/

사용법:
  # 운용서버 (Docker exec)
  docker exec -it web python manage.py import_all_data

  # 폴더 지정
  docker exec -it web python manage.py import_all_data --data-dir /app/nas/media/npms/data

  # 미리보기 (실제 저장 안 함)
  docker exec -it web python manage.py import_all_data --dry-run

  # 이미 있는 데이터도 업데이트
  docker exec -it web python manage.py import_all_data --update

  # 특정 단계만 실행 (콤마 구분)
  docker exec -it web python manage.py import_all_data --only schools,workers
"""
import os
from django.core.management.base import BaseCommand
from django.core.management import call_command


# ── 임포트 단계 정의 ────────────────────────────────────────────
# (단계키, 파일명, 커맨드명, 커맨드 추가 kwargs)
STEPS = [
    # 1. JSON fixture (코드 내 포함 — 파일 불필요)
    {
        'key':     'fixtures',
        'label':   '[1] 지원청/학제/장애분류 기초데이터 (fixture)',
        'file':    None,
        'command': 'load_initial_data',
        'kwargs':  {},
    },
    # 2. 학교정보
    {
        'key':     'schools',
        'label':   '[2] 학교정보',
        'file':    '학교정보.xlsx',
        'command': 'load_schools',
        'kwargs':  {'update': True},
    },
    # 3. 선생님(담당자) 정보
    {
        'key':     'teachers',
        'label':   '[3] 선생님/담당자 정보',
        'file':    '선생님정보.xlsx',
        'command': 'import_teacher_contacts',
        'kwargs':  {},
    },
    # 4. 인력(사용자)
    {
        'key':     'workers',
        'label':   '[4] 인력(사용자)',
        'file':    '인력.xlsx',
        'command': 'import_workers',
        'kwargs':  {'update': True},
    },
    # 5. 자재내역
    {
        'key':     'materials',
        'label':   '[5] 자재내역',
        'file':    '자재내역.xlsx',
        'command': 'import_materials',
        'kwargs':  {'update': True},
    },
    # 6. 장비목록 → school_equipment (xlsm 우선, 없으면 xlsx)
    {
        'key':     'equipment',
        'label':   '[6] 장비목록 → school_equipment',
        'file':    '장비목록.xlsm',
        'file_alt':'장비목록.xlsx',
        'command': 'import_equipment',
        'kwargs':  {},
    },
    # 7. school_equipment building/floor 분리
    {
        'key':     'split_location',
        'label':   '[7] school_equipment 설치장소 분리 (building/floor)',
        'file':    None,
        'command': 'split_install_location',
        'kwargs':  {},
    },
    # 8. 장비목록 → assets (장비 자산관리)
    {
        'key':     'assets',
        'label':   '[8] 장비목록 → assets',
        'file':    '장비목록.xlsx',
        'file_alt':'장비목록.xlsm',
        'command': 'import_assets',
        'kwargs':  {'update': True},
    },
    # 9. 정기점검 (선택)
    {
        'key':     'inspection',
        'label':   '[9] 정기점검 (선택)',
        'file':    '정기점검.xlsx',
        'command': 'import_inspection',
        'kwargs':  {},
        'optional': True,
    },
]


class Command(BaseCommand):
    help = '운용서버 기초 DB 일괄 임포트 (data 폴더 → 순서대로 자동 처리)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--data-dir', default=None,
            help='Excel 파일 폴더 경로 (기본: NAS_MEDIA_ROOT/data 또는 BASE_DIR/media/data)'
        )
        parser.add_argument(
            '--dry-run', action='store_true', dest='dry_run',
            help='실제 DB 저장 없이 미리보기'
        )
        parser.add_argument(
            '--update', action='store_true',
            help='이미 존재하는 데이터도 업데이트'
        )
        parser.add_argument(
            '--only', default='',
            help='특정 단계만 실행 (콤마 구분, 예: schools,workers,equipment)'
        )
        parser.add_argument(
            '--skip', default='',
            help='특정 단계 건너뜀 (콤마 구분, 예: assets,inspection)'
        )

    def handle(self, *args, **options):
        from django.conf import settings

        # ── 데이터 폴더 결정 ──────────────────────────────────────
        data_dir = options['data_dir']
        if not data_dir:
            # 운용서버: NAS_MEDIA_ROOT 우선
            nas_root = getattr(settings, 'NAS_MEDIA_ROOT', None)
            if nas_root and os.path.isdir(nas_root):
                data_dir = os.path.join(nas_root, 'data')
            else:
                data_dir = os.path.join(settings.BASE_DIR, 'media', 'data')

        self.stdout.write('=' * 60)
        self.stdout.write(f'데이터 폴더: {data_dir}')
        if not os.path.isdir(data_dir):
            self.stderr.write(
                self.style.ERROR(f'폴더가 존재하지 않습니다: {data_dir}')
            )
            self.stderr.write('  → 폴더를 만들고 Excel 파일을 넣은 뒤 재실행하세요.')
            return

        dry_run   = options['dry_run']
        do_update = options['update']

        # 실행할/건너뛸 단계 필터
        only_keys = {k.strip() for k in options['only'].split(',') if k.strip()}
        skip_keys = {k.strip() for k in options['skip'].split(',') if k.strip()}

        if dry_run:
            self.stdout.write(self.style.WARNING('** DRY-RUN — 실제 저장 안 함 **'))

        # ── 폴더 파일 목록 출력 ───────────────────────────────────
        files_in_dir = set(os.listdir(data_dir))
        self.stdout.write(f'\n폴더 내 파일: {sorted(files_in_dir) or "(없음)"}')
        self.stdout.write('=' * 60 + '\n')

        ok_steps = err_steps = skip_steps = 0

        for step in STEPS:
            key     = step['key']
            label   = step['label']
            file_name = step.get('file')
            file_alt  = step.get('file_alt')
            command = step['command']
            optional = step.get('optional', False)

            # 단계 필터
            if only_keys and key not in only_keys:
                continue
            if key in skip_keys:
                self.stdout.write(f'{label} → 건너뜀 (--skip)')
                skip_steps += 1
                continue

            self.stdout.write(self.style.MIGRATE_HEADING(label))

            # 파일 경로 결정
            file_path = None
            if file_name:
                candidate = os.path.join(data_dir, file_name)
                alt       = os.path.join(data_dir, file_alt) if file_alt else None

                if os.path.exists(candidate):
                    file_path = candidate
                elif alt and os.path.exists(alt):
                    file_path = alt
                    self.stdout.write(f'  (기본파일 없음, 대체파일 사용: {file_alt})')
                else:
                    if optional:
                        self.stdout.write(f'  파일 없음 — 선택 항목이므로 건너뜀: {file_name}')
                        skip_steps += 1
                    else:
                        self.stdout.write(
                            self.style.WARNING(f'  ⚠ 파일 없음: {file_name} — 이 단계를 건너뜁니다.')
                        )
                        skip_steps += 1
                    self.stdout.write('')
                    continue

            # kwargs 구성
            kwargs = dict(step['kwargs'])
            if dry_run:
                kwargs['dry_run'] = True
            if do_update and 'update' in step['kwargs']:
                kwargs['update'] = True
            if file_path:
                kwargs['file'] = file_path

            # 커맨드 실행
            try:
                call_command(command, **kwargs)
                ok_steps += 1
                self.stdout.write(self.style.SUCCESS(f'  ✓ 완료\n'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  ✗ 오류: {e}\n'))
                err_steps += 1

        # ── 최종 요약 ────────────────────────────────────────────
        self.stdout.write('=' * 60)
        self.stdout.write(self.style.SUCCESS(
            f'전체 완료 — 성공: {ok_steps}단계 / 오류: {err_steps}단계 / 건너뜀: {skip_steps}단계'
        ))
        if dry_run:
            self.stdout.write(self.style.WARNING('** DRY-RUN — 실제 DB는 변경되지 않았습니다 **'))
