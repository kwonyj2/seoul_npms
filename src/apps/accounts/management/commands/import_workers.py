"""
인력.xlsx → accounts.User 임포트

컬럼 (자동 감지):
  username / 아이디, 이름 / 성명, 역할, 연락처 / 전화번호,
  이메일, 지원청 / 교육지원청, 자택주소, 초기비밀번호

사용법:
  python manage.py import_workers
  python manage.py import_workers --file /path/to/인력.xlsx
  python manage.py import_workers --update   # 이미 있는 사용자도 업데이트
  python manage.py import_workers --dry-run
"""
import os
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

ROLE_MAP = {
    '슈퍼관리자': 'superadmin',
    '관리자':    'admin',
    '현장기사':  'worker',
    '기사':      'worker',
    '상주인력':  'resident',
    '상주':      'resident',
    '학교담당자': 'customer',
    '고객':      'customer',
    'superadmin': 'superadmin',
    'admin':      'admin',
    'worker':     'worker',
    'resident':   'resident',
    'customer':   'customer',
}

CENTER_MAP = {
    '동부': '동부교육지원청',
    '서부': '서부교육지원청',
    '남부': '남부교육지원청',
    '북부': '북부교육지원청',
    '중부': '중부교육지원청',
    '강동송파': '강동송파교육지원청',
    '강서양천': '강서양천교육지원청',
    '강남서초': '강남서초교육지원청',
    '동작관악': '동작관악교육지원청',
    '성동광진': '성동광진교육지원청',
    '성북강북': '성북강북교육지원청',
}


class Command(BaseCommand):
    help = '인력.xlsx 파일을 읽어 accounts.User 테이블에 등록합니다.'

    def add_arguments(self, parser):
        parser.add_argument('--file', default=None, help='xlsx 파일 경로 (기본: media/data/인력.xlsx)')
        parser.add_argument('--update', action='store_true', help='이미 존재하는 사용자도 업데이트')
        parser.add_argument('--dry-run', action='store_true', dest='dry_run', help='DB 저장 없이 미리보기')
        parser.add_argument('--default-password', default='npms1234!', help='초기 비밀번호 (기본: npms1234!)')

    def handle(self, *args, **options):
        try:
            import openpyxl
        except ImportError:
            raise CommandError('openpyxl 미설치. pip install openpyxl')

        from apps.accounts.models import User
        from apps.schools.models import SupportCenter

        file_path = options['file']
        if not file_path:
            from django.conf import settings
            nas_root = getattr(settings, 'NAS_MEDIA_ROOT', None)
            candidates = []
            if nas_root:
                candidates.append(os.path.join(nas_root, 'data', '인력.xlsx'))
            candidates.append(os.path.join(settings.BASE_DIR, 'media', 'data', '인력.xlsx'))
            file_path = next((p for p in candidates if os.path.exists(p)), candidates[0])

        if not os.path.exists(file_path):
            raise CommandError(f'파일 없음: {file_path}')

        dry_run   = options['dry_run']
        do_update = options['update']
        default_pw = options['default_password']

        self.stdout.write(f'파일: {file_path}')
        if dry_run:
            self.stdout.write(self.style.WARNING('** DRY-RUN — DB 저장하지 않음 **'))

        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            self.stdout.write(self.style.WARNING('데이터 없음'))
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
            'username': idx('username', '아이디', '사용자명', '로그인ID'),
            'name':     idx('이름', '성명', 'name'),
            'role':     idx('역할', '권한', 'role'),
            'phone':    idx('연락처', '전화번호', '휴대폰', 'phone'),
            'email':    idx('이메일', 'email'),
            'center':   idx('지원청', '교육지원청', '소속지원청', '소속', 'center'),
            'address':  idx('자택주소', '주소', 'address'),
            'password': idx('비밀번호', '초기비밀번호', '비밀번호(신규등록용)', 'password'),
        }
        self.stdout.write(f'컬럼 매핑: {COL}')

        # SupportCenter 캐시
        center_cache = {}
        for sc in SupportCenter.objects.all():
            center_cache[sc.name] = sc
            # 단축명 매핑
            for short, full in CENTER_MAP.items():
                if full == sc.name:
                    center_cache[short] = sc

        def get(row, key):
            i = COL.get(key)
            if i is None or i >= len(row):
                return ''
            v = row[i]
            return str(v).strip() if v is not None else ''

        created = updated = skipped = error = 0

        with transaction.atomic():
            for row_num, row in enumerate(rows[1:], start=2):
                if not any(row):
                    continue

                username = get(row, 'username')
                name     = get(row, 'name')
                if not username and not name:
                    continue

                # username 없으면 이름으로 자동 생성
                if not username:
                    username = name.replace(' ', '').lower() if name else f'user{row_num}'

                role_raw = get(row, 'role')
                role     = ROLE_MAP.get(role_raw, 'worker')
                email    = get(row, 'email') or f'{username}@npms.local'
                phone    = get(row, 'phone')
                address  = get(row, 'address')
                pw       = get(row, 'password') or default_pw

                # 지원청 매핑
                center_raw = get(row, 'center')
                center_obj = None
                for key in [center_raw] + [k for k in CENTER_MAP if k in center_raw]:
                    if key in center_cache:
                        center_obj = center_cache[key]
                        break

                if dry_run:
                    self.stdout.write(
                        f'  [행{row_num}] {username} / {name} / {role} / {center_raw} → {center_obj}'
                    )
                    created += 1
                    continue

                try:
                    existing = User.objects.filter(username=username).first()
                    if existing:
                        if do_update:
                            existing.name           = name or existing.name
                            existing.role           = role
                            existing.phone          = phone or existing.phone
                            existing.email          = email
                            existing.home_address   = address or existing.home_address
                            existing.support_center = center_obj or existing.support_center
                            existing.save()
                            updated += 1
                        else:
                            skipped += 1
                    else:
                        user = User(
                            username=username,
                            name=name or username,
                            email=email,
                            role=role,
                            phone=phone,
                            home_address=address,
                            support_center=center_obj,
                            is_active=True,
                        )
                        user.set_password(pw)
                        user.save()
                        created += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'  [행{row_num}] 오류: {e}'))
                    error += 1

        self.stdout.write(self.style.SUCCESS(
            f'\n완료 — 생성: {created}명 / 업데이트: {updated}명 / 스킵: {skipped}명 / 오류: {error}명'
        ))
