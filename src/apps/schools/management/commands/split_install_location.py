"""
school_equipment 테이블의 install_location 값을 building / floor / install_location 3개 컬럼으로 분리

현황: Excel 임포트 시 건물/층수 컬럼이 비어 있고
      설치장소에 '본관 2층 전산실' 형태로 합쳐 저장됨

패턴: '<건물명> <층수> <설치장소>'
  예) '본관 2층 전산실'  → building='본관',  floor='2층',  install_location='전산실'
      '신관 1층 서버실'  → building='신관',  floor='1층',  install_location='서버실'
      '별관 지하1층 MDF' → building='별관',  floor='지하1층', install_location='MDF'

Usage:
  python manage.py split_install_location          # 실제 적용
  python manage.py split_install_location --dry-run  # 미리보기만
  python manage.py split_install_location --school 123  # 특정 학교만
"""
import re
from django.core.management.base import BaseCommand


# 층수 패턴: '2층', '지하1층', 'B1층' 등
_FLOOR_PAT = r'(지하\d+층|B\d+층|\d+층)'
# 건물명 + 층수 + 설치장소 분리
_SPLIT_RE = re.compile(r'^(.+?)\s+' + _FLOOR_PAT + r'\s+(.+)$')


def _parse(location: str):
    """'본관 2층 전산실' → ('본관', '2층', '전산실') 또는 None"""
    m = _SPLIT_RE.match(location.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
    return None


class Command(BaseCommand):
    help = 'school_equipment.install_location 을 building/floor/install_location 3컬럼으로 분리'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='변경 없이 결과만 출력')
        parser.add_argument('--school', type=int, default=None, help='특정 school_id만 처리')
        parser.add_argument('--force', action='store_true',
                            help='building이 이미 있는 레코드도 재처리')

    def handle(self, *args, **options):
        from apps.schools.models import SchoolEquipment

        dry_run  = options['dry_run']
        school_id = options['school']
        force    = options['force']

        qs = SchoolEquipment.objects.all()
        if school_id:
            qs = qs.filter(school_id=school_id)
        if not force:
            # building이 비어 있는 레코드만 대상
            qs = qs.filter(building='')

        total   = qs.count()
        self.stdout.write(f'대상 레코드: {total}건  (dry_run={dry_run})')

        updated   = []
        unmatched = []

        for eq in qs.iterator(chunk_size=500):
            loc = eq.install_location
            if not loc:
                continue

            parsed = _parse(loc)
            if parsed:
                bld, flr, place = parsed
                if dry_run:
                    self.stdout.write(
                        f'  [변경예정] id={eq.id} | "{loc}"'
                        f' → building="{bld}" floor="{flr}" install_location="{place}"'
                    )
                else:
                    eq.building          = bld
                    eq.floor             = flr
                    eq.install_location  = place
                    updated.append(eq)
            else:
                unmatched.append((eq.id, loc))

        # bulk_update
        if not dry_run and updated:
            SchoolEquipment.objects.bulk_update(
                updated, ['building', 'floor', 'install_location'], batch_size=500
            )

        self.stdout.write(self.style.SUCCESS(
            f'완료 — 분리 처리: {len(updated)}건'
            + (' (dry-run, 실제 저장 안 함)' if dry_run else '')
        ))

        if unmatched:
            self.stdout.write(self.style.WARNING(
                f'패턴 불일치 (수동 확인 필요): {len(unmatched)}건'
            ))
            for eid, loc in unmatched[:30]:
                self.stdout.write(f'  id={eid} install_location="{loc}"')
            if len(unmatched) > 30:
                self.stdout.write(f'  ... 외 {len(unmatched) - 30}건')
