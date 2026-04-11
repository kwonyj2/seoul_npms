"""
자재내역.xlsx → materials.Material + WarehouseInventory 임포트

컬럼 (자동 감지):
  자재코드, 자재명, 분류, 규격/사양, 단위, 단가, 최소재고, 재고수량, 공급업체, 비고

사용법:
  python manage.py import_materials
  python manage.py import_materials --file /path/to/자재내역.xlsx
  python manage.py import_materials --update
  python manage.py import_materials --dry-run
"""
import os
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

CATEGORY_TYPE_MAP = {
    '케이블':       'cable',
    '커넥터':       'connector',
    '잭':          'connector',
    '공구':         'tool',
    '장비':         'equipment',
    '기타':         'other',
}

UNIT_MAP = {
    '개':   'ea', 'EA': 'ea', 'ea': 'ea',
    '미터': 'm',  'm':  'm',  'M':  'm',
    '롤':   'roll', 'Roll': 'roll', 'roll': 'roll',
    '세트': 'set',  'Set':  'set',  'set':  'set',
    '박스': 'box',  'Box':  'box',  'box':  'box',
}


class Command(BaseCommand):
    help = '자재내역.xlsx 를 읽어 materials.Material + WarehouseInventory 에 등록합니다.'

    def add_arguments(self, parser):
        parser.add_argument('--file', default=None)
        parser.add_argument('--update', action='store_true')
        parser.add_argument('--dry-run', action='store_true', dest='dry_run')

    def handle(self, *args, **options):
        try:
            import openpyxl
        except ImportError:
            raise CommandError('openpyxl 미설치.')

        from apps.materials.models import Material, MaterialCategory, WarehouseInventory

        file_path = options['file']
        if not file_path:
            from django.conf import settings
            nas_root = getattr(settings, 'NAS_MEDIA_ROOT', None)
            candidates = []
            if nas_root:
                candidates.append(os.path.join(nas_root, 'data', '자재내역.xlsx'))
            candidates.append(os.path.join(settings.BASE_DIR, 'media', 'data', '자재내역.xlsx'))
            file_path = next((p for p in candidates if os.path.exists(p)), candidates[0])

        if not os.path.exists(file_path):
            raise CommandError(f'파일 없음: {file_path}')

        dry_run   = options['dry_run']
        do_update = options['update']

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

        def idx(*names):
            for n in names:
                try:
                    return headers.index(n)
                except ValueError:
                    pass
            return None

        COL = {
            'code':     idx('자재코드', '코드', 'code'),
            'name':     idx('자재명', '품명', '품목', '이름', 'name'),
            'category': idx('분류', '카테고리', '구분', 'category'),
            'spec':     idx('규격', '사양', '규격/사양', 'spec'),
            'unit':     idx('단위', 'unit'),
            'price':    idx('단가', '단가(원)', 'price'),
            'min_stock':idx('최소재고', '안전재고', 'min_stock'),
            'quantity': idx('재고수량', '현재고', '수량', 'quantity'),
            'supplier': idx('공급업체', '업체', 'supplier'),
            'note':     idx('비고', 'note'),
        }
        self.stdout.write(f'컬럼 매핑: {COL}')

        def get(row, key):
            i = COL.get(key)
            if i is None or i >= len(row):
                return ''
            v = row[i]
            return str(v).strip() if v is not None else ''

        def get_num(row, key, default=0):
            s = get(row, key)
            try:
                return int(float(s.replace(',', '')))
            except (ValueError, AttributeError):
                return default

        # 카테고리 캐시
        cat_cache = {}
        for cat in MaterialCategory.objects.all():
            cat_cache[cat.code] = cat
            cat_cache[cat.name] = cat

        def get_or_create_category(cat_name):
            if not cat_name:
                cat_name = '기타'
            if cat_name in cat_cache:
                return cat_cache[cat_name]
            type_code = CATEGORY_TYPE_MAP.get(cat_name, 'other')
            code = cat_name[:20].lower().replace(' ', '_')
            if dry_run:
                return None
            cat, _ = MaterialCategory.objects.get_or_create(
                name=cat_name,
                defaults={'code': code, 'type_code': type_code, 'order': 99}
            )
            cat_cache[cat_name] = cat
            return cat

        # 자재코드 자동생성 카운터
        auto_code_seq = [Material.objects.count() + 1]

        def make_code(name):
            code = f'MAT{auto_code_seq[0]:04d}'
            auto_code_seq[0] += 1
            return code

        created = updated = skipped = error = 0

        with transaction.atomic():
            for row_num, row in enumerate(rows[1:], start=2):
                if not any(row):
                    continue

                mat_name = get(row, 'name')
                if not mat_name:
                    continue

                mat_code    = get(row, 'code') or make_code(mat_name)
                cat_name    = get(row, 'category')
                spec        = get(row, 'spec')
                unit_raw    = get(row, 'unit')
                unit        = UNIT_MAP.get(unit_raw, 'ea')
                price       = get_num(row, 'price')
                min_stock   = get_num(row, 'min_stock')
                quantity    = get_num(row, 'quantity')
                supplier    = get(row, 'supplier')
                note        = get(row, 'note')

                if dry_run:
                    self.stdout.write(
                        f'  [행{row_num}] {mat_code} | {mat_name} | {cat_name} | {unit} | 단가:{price} | 재고:{quantity}'
                    )
                    created += 1
                    continue

                try:
                    cat_obj = get_or_create_category(cat_name)
                    existing = Material.objects.filter(code=mat_code).first()
                    if not existing:
                        existing = Material.objects.filter(name=mat_name).first()

                    if existing:
                        if do_update:
                            existing.name     = mat_name
                            existing.spec     = spec
                            existing.unit     = unit
                            existing.unit_price = price
                            existing.min_stock  = min_stock
                            existing.supplier   = supplier
                            existing.note       = note
                            if cat_obj:
                                existing.category = cat_obj
                            existing.save()
                            # 재고 업데이트
                            if quantity:
                                inv, _ = WarehouseInventory.objects.get_or_create(material=existing)
                                inv.quantity = quantity
                                inv.save()
                            updated += 1
                        else:
                            skipped += 1
                    else:
                        if cat_obj is None:
                            cat_obj, _ = MaterialCategory.objects.get_or_create(
                                name='기타', defaults={'code': 'other', 'type_code': 'other'}
                            )
                        mat = Material.objects.create(
                            code=mat_code,
                            name=mat_name,
                            category=cat_obj,
                            spec=spec,
                            unit=unit,
                            unit_price=price,
                            min_stock=min_stock,
                            supplier=supplier,
                            note=note,
                        )
                        if quantity:
                            WarehouseInventory.objects.create(material=mat, quantity=quantity)
                        created += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f'  [행{row_num}] 오류: {e}'))
                    error += 1

        self.stdout.write(self.style.SUCCESS(
            f'\n완료 — 생성: {created}개 / 업데이트: {updated}개 / 스킵: {skipped}개 / 오류: {error}개'
        ))
