"""
장비목록.xlsx → school_equipment 테이블 임포트
Usage: python manage.py import_equipment --file /path/to/장비목록.xlsm --clear
"""
from django.core.management.base import BaseCommand
from django.conf import settings
import os


def _normalize_category(val):
    """'   스위치 ' → '스위치',  'POE'/'PoE'/'   POE' → 'PoE스위치'"""
    v = (val or '').strip()
    vu = v.upper()
    if 'POE' in vu or 'PoE' in v:
        return 'PoE스위치'
    if '스위치' in v:
        return '스위치'
    return v


def _normalize_network(val):
    """앞뒤 공백 제거"""
    return (val or '').strip()


class Command(BaseCommand):
    help = '장비목록.xlsx(m)를 school_equipment 테이블로 임포트'

    def add_arguments(self, parser):
        parser.add_argument('--file', default=None, help='xlsx/xlsm 파일 경로')
        parser.add_argument('--clear', action='store_true', help='임포트 전 기존 데이터 삭제')

    def handle(self, *args, **options):
        import openpyxl
        from apps.schools.models import School, SchoolEquipment

        xlsx_path = options['file'] or os.path.join(settings.MEDIA_ROOT, 'data', '장비목록.xlsm')
        if not os.path.exists(xlsx_path):
            # fallback to .xlsx
            alt = xlsx_path.replace('.xlsm', '.xlsx')
            if os.path.exists(alt):
                xlsx_path = alt
            else:
                self.stderr.write(f'파일 없음: {xlsx_path}')
                return

        self.stdout.write(f'파일 로드: {xlsx_path}')
        wb = openpyxl.load_workbook(xlsx_path, read_only=True, keep_vba=False, data_only=True)
        ws = wb.worksheets[0]
        rows = ws.iter_rows(values_only=True)
        headers = [str(h).strip() if h else '' for h in next(rows)]
        self.stdout.write(f'헤더: {headers}')

        def idx(name):
            try:
                return headers.index(name)
            except ValueError:
                return None

        COL = {
            'center':    idx('지원청'),
            'school':    idx('학교명'),
            'building':  idx('건물'),
            'floor':     idx('층수'),
            'category':  idx('구분'),
            'model':     idx('모델명'),
            'mfr':       idx('제조사'),
            'location':  idx('설치장소'),
            'dev_id':    idx('장비 ID'),
            'net_type':  idx('망구분'),
            'speed':     idx('속도'),
            'tier':      idx('계위'),
            'origin':    idx('국산/외산'),
            'mgmt':      idx('MGMT(관리)(Y/N)') or idx('MGMT'),
            'year':      idx('도입년도') or idx('도입년'),
        }

        if options['clear']:
            SchoolEquipment.objects.all().delete()
            self.stdout.write('기존 데이터 삭제 완료')

        # 학교 캐시
        school_cache = {}
        for s in School.objects.select_related('support_center').iterator():
            school_cache[(s.support_center.name, s.name)] = s
            school_cache[('*', s.name)] = s

        def get_val(row, key):
            i = COL.get(key)
            if i is None or i >= len(row):
                return ''
            v = row[i]
            return str(v).strip() if v is not None else ''

        BATCH = 2000
        bulk = []
        created = skipped = 0

        for row in rows:
            if not any(row):
                continue
            center_name = get_val(row, 'center')
            school_name = get_val(row, 'school')
            if not school_name:
                skipped += 1
                continue

            school = school_cache.get((center_name, school_name)) or \
                     school_cache.get(('*', school_name))
            if not school:
                skipped += 1
                continue

            # 구분 정규화 — 스위치/PoE스위치 이외 항목도 저장
            raw_cat = get_val(row, 'category')
            category = _normalize_category(raw_cat)

            # 도입년도
            year = None
            yi = COL.get('year')
            if yi is not None and yi < len(row) and row[yi]:
                try:
                    year = int(row[yi])
                except (ValueError, TypeError):
                    year = None

            # 층수: 숫자일 수 있으므로 문자열 변환
            floor_raw = get_val(row, 'floor')
            if floor_raw and floor_raw != 'None':
                try:
                    floor_val = str(int(float(floor_raw))) + '층'
                except (ValueError, TypeError):
                    floor_val = floor_raw
            else:
                floor_val = ''

            bulk.append(SchoolEquipment(
                school=school,
                category=category,
                model_name=get_val(row, 'model'),
                manufacturer=get_val(row, 'mfr'),
                building=get_val(row, 'building'),
                floor=floor_val,
                install_location=get_val(row, 'location'),
                device_id=get_val(row, 'dev_id'),
                network_type=_normalize_network(get_val(row, 'net_type')),
                speed=get_val(row, 'speed'),
                tier=get_val(row, 'tier'),
                origin=get_val(row, 'origin'),
                mgmt=get_val(row, 'mgmt'),
                install_year=year,
            ))
            created += 1

            if len(bulk) >= BATCH:
                SchoolEquipment.objects.bulk_create(bulk, ignore_conflicts=True)
                bulk = []
                self.stdout.write(f'  {created}건 처리 중...')

        if bulk:
            SchoolEquipment.objects.bulk_create(bulk, ignore_conflicts=True)

        self.stdout.write(self.style.SUCCESS(
            f'완료 — 등록: {created}건, 스킵(학교불일치): {skipped}건'
        ))
