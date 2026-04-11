"""
장비목록.xlsx → assets.Asset (+ AssetModel, AssetCategory) 임포트

컬럼 (자동 감지):
  지원청, 학교명, 구분, 모델명, 제조사, 설치장소, 장비 ID, 망구분, 속도, 계위, 국산/외산, MGMT, 도입년

사용법:
  python manage.py import_assets
  python manage.py import_assets --file /path/to/장비목록.xlsx
  python manage.py import_assets --update
  python manage.py import_assets --dry-run
  python manage.py import_assets --batch 500   # bulk_create 배치 크기 (기본 200)
"""
import os
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

# 장비 구분 → AssetCategory.code 매핑
CATEGORY_MAP = {
    '스위치':   'switch',
    'L2 스위치': 'switch',
    'L3 스위치': 'switch',
    'PoE':     'poe_switch',
    'PoE스위치': 'poe_switch',
    'AP':      'ap',
    '무선AP':   'ap',
    '라우터':   'router',
    '서버':     'server',
}


class Command(BaseCommand):
    help = '장비목록.xlsx 를 읽어 assets.Asset 테이블에 등록합니다.'

    def add_arguments(self, parser):
        parser.add_argument('--file',    default=None)
        parser.add_argument('--update',  action='store_true')
        parser.add_argument('--dry-run', action='store_true', dest='dry_run')
        parser.add_argument('--batch',   type=int, default=200, help='bulk_create 배치 크기')

    def handle(self, *args, **options):
        try:
            import openpyxl
        except ImportError:
            raise CommandError('openpyxl 미설치.')

        from apps.assets.models import Asset, AssetModel, AssetCategory

        file_path = options['file']
        if not file_path:
            from django.conf import settings
            nas_root = getattr(settings, 'NAS_MEDIA_ROOT', None)
            candidates = []
            if nas_root:
                candidates.append(os.path.join(nas_root, 'data', '장비목록.xlsx'))
                candidates.append(os.path.join(nas_root, 'data', '장비목록.xlsm'))
            candidates.append(os.path.join(settings.BASE_DIR, 'media', 'data', '장비목록.xlsx'))
            file_path = next((p for p in candidates if os.path.exists(p)), candidates[0])

        if not os.path.exists(file_path):
            raise CommandError(f'파일 없음: {file_path}')

        dry_run   = options['dry_run']
        do_update = options['update']
        batch_size = options['batch']

        self.stdout.write(f'파일: {file_path}')
        if dry_run:
            self.stdout.write(self.style.WARNING('** DRY-RUN **'))

        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            self.stdout.write('데이터 없음')
            return

        headers = [str(h).strip() if h else '' for h in rows[0]]
        self.stdout.write(f'헤더: {headers}')
        self.stdout.write(f'전체 행수: {len(rows) - 1:,}')

        def idx(*names):
            for n in names:
                try:
                    return headers.index(n)
                except ValueError:
                    pass
            return None

        COL = {
            'district':  idx('지원청', '교육지원청', 'district'),
            'school':    idx('학교명', '학교', 'school'),
            'category':  idx('구분', '장비구분', 'type'),
            'model':     idx('모델명', '모델', 'model'),
            'maker':     idx('제조사', '제조사명', 'manufacturer'),
            'location':  idx('설치장소', '설치위치', 'location'),
            'device_id': idx('장비 ID', '장비ID', 'device_id', 'ID'),
            'network':   idx('망구분', '망', 'network'),
            'speed':     idx('속도', 'speed'),
            'tier':      idx('계위', 'tier'),
            'origin':    idx('국산/외산', '국산외산', 'origin'),
            'mgmt':      idx('MGMT', 'mgmt', 'Mgmt'),
            'year':      idx('도입년', '설치년도', '도입연도', 'year'),
        }
        self.stdout.write(f'컬럼 매핑: {COL}')

        def get(row, key):
            i = COL.get(key)
            if i is None or i >= len(row):
                return ''
            v = row[i]
            return str(v).strip() if v is not None else ''

        def get_year(row):
            s = get(row, 'year')
            try:
                return int(float(s))
            except (ValueError, AttributeError):
                return None

        # ── 캐시 ──────────────────────────────────────────────────
        from apps.schools.models import School, SupportCenter

        school_cache  = {s.name: s for s in School.objects.all()}
        center_cache  = {c.name: c for c in SupportCenter.objects.all()}
        # 단축명 매핑
        for c in SupportCenter.objects.all():
            short = c.name.replace('교육지원청', '')
            if short:
                center_cache[short] = c

        # AssetCategory 캐시
        cat_cache = {c.code: c for c in AssetCategory.objects.all()}

        # AssetModel 캐시 (manufacturer+model_name)
        model_cache = {
            (m.manufacturer, m.model_name): m
            for m in AssetModel.objects.select_related('category').all()
        }

        # 기존 serial_number 집합
        existing_sns = set(Asset.objects.values_list('serial_number', flat=True))

        def get_or_create_category(cat_raw):
            code = 'switch'
            for k, v in CATEGORY_MAP.items():
                if k in cat_raw:
                    code = v
                    break
            if code in cat_cache:
                return cat_cache[code]
            # 기본값으로 switch 카테고리
            cat = AssetCategory.objects.filter(code='switch').first()
            if cat:
                cat_cache[code] = cat
            return cat

        def get_or_create_model(maker, model_name, cat_raw):
            key = (maker, model_name)
            if key in model_cache:
                return model_cache[key]
            if dry_run:
                return None
            cat = get_or_create_category(cat_raw)
            am, _ = AssetModel.objects.get_or_create(
                manufacturer=maker,
                model_name=model_name,
                defaults={'category': cat or AssetCategory.objects.first()}
            )
            model_cache[key] = am
            return am

        created = updated = skipped = error = 0
        to_create = []

        def flush(force=False):
            nonlocal created
            if not to_create:
                return
            if force or len(to_create) >= batch_size:
                Asset.objects.bulk_create(to_create, ignore_conflicts=True)
                created += len(to_create)
                if created % 5000 == 0 or force:
                    self.stdout.write(f'  진행: {created:,}개 등록...')
                to_create.clear()

        with transaction.atomic():
            for row_num, row in enumerate(rows[1:], start=2):
                if not any(row):
                    continue

                device_id = get(row, 'device_id')
                if not device_id:
                    continue

                model_name  = get(row, 'model')
                maker       = get(row, 'maker') or '미상'
                cat_raw     = get(row, 'category') or '스위치'
                school_name = get(row, 'school')
                district    = get(row, 'district')
                location    = get(row, 'location')
                install_yr  = get_year(row)
                network     = get(row, 'network')
                speed       = get(row, 'speed')
                tier        = get(row, 'tier')
                origin      = get(row, 'origin')
                mgmt        = get(row, 'mgmt')

                note_parts = [p for p in [
                    f'망:{network}'   if network else '',
                    f'속도:{speed}'   if speed   else '',
                    f'계위:{tier}'    if tier    else '',
                    f'구분:{origin}'  if origin  else '',
                    f'MGMT:{mgmt}'   if mgmt    else '',
                ] if p]
                note = ' / '.join(note_parts)

                if dry_run:
                    self.stdout.write(
                        f'  [행{row_num}] {device_id} | {maker} {model_name} | {school_name} | {location}'
                    )
                    created += 1
                    continue

                try:
                    if device_id in existing_sns:
                        if do_update:
                            asset = Asset.objects.get(serial_number=device_id)
                            asset.install_location = location
                            asset.install_year     = install_yr
                            asset.note             = note
                            school = school_cache.get(school_name)
                            if school:
                                asset.current_school = school
                                asset.status = 'installed'
                            center = center_cache.get(district, center_cache.get(district + '교육지원청'))
                            if center:
                                asset.current_center = center
                            asset.save()
                            updated += 1
                        else:
                            skipped += 1
                        continue

                    asset_model = get_or_create_model(maker, model_name, cat_raw)
                    if not asset_model:
                        skipped += 1
                        continue

                    school = school_cache.get(school_name)
                    center = center_cache.get(district) or center_cache.get(district + '교육지원청')
                    status = 'installed' if school else ('center' if center else 'warehouse')

                    to_create.append(Asset(
                        asset_model=asset_model,
                        serial_number=device_id,
                        status=status,
                        current_school=school,
                        current_center=center,
                        install_location=location,
                        install_year=install_yr,
                        note=note,
                    ))
                    existing_sns.add(device_id)
                    flush()

                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'  [행{row_num}] 오류: {e}'))
                    error += 1

            flush(force=True)

        self.stdout.write(self.style.SUCCESS(
            f'\n완료 — 생성: {created:,}개 / 업데이트: {updated:,}개 / 스킵: {skipped:,}개 / 오류: {error:,}개'
        ))
