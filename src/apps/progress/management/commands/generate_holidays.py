"""
management command: generate_holidays
매년 음력 공휴일(설날·부처님오신날·추석) + 대체공휴일을 자동 생성.
usage: python manage.py generate_holidays          # 올해+내년
       python manage.py generate_holidays --year 2027
"""
from datetime import date, timedelta
from django.core.management.base import BaseCommand


# ── 음력 공휴일 양력 날짜 룩업 (2026~2040) ────────────────────────
# 설날(음력1/1), 부처님오신날(음력4/8), 추석(음력8/15)
LUNAR_DATES = {
    2026: {'seollal': date(2026,  2, 17), 'buddha': date(2026,  5, 24), 'chuseok': date(2026, 10,  4)},
    2027: {'seollal': date(2027,  2,  6), 'buddha': date(2027,  5, 13), 'chuseok': date(2027,  9, 23)},
    2028: {'seollal': date(2028,  1, 26), 'buddha': date(2028,  5,  2), 'chuseok': date(2028, 10, 11)},
    2029: {'seollal': date(2029,  2, 13), 'buddha': date(2029,  5, 20), 'chuseok': date(2029,  9, 30)},
    2030: {'seollal': date(2030,  2,  3), 'buddha': date(2030,  5,  9), 'chuseok': date(2030,  9, 19)},
    2031: {'seollal': date(2031,  1, 23), 'buddha': date(2031,  5, 28), 'chuseok': date(2031, 10,  8)},
    2032: {'seollal': date(2032,  2, 11), 'buddha': date(2032,  5, 16), 'chuseok': date(2032,  9, 26)},
    2033: {'seollal': date(2033,  1, 31), 'buddha': date(2033,  5,  6), 'chuseok': date(2033,  9, 15)},
    2034: {'seollal': date(2034,  2, 19), 'buddha': date(2034,  5, 25), 'chuseok': date(2034, 10,  4)},
    2035: {'seollal': date(2035,  2,  8), 'buddha': date(2035,  5, 15), 'chuseok': date(2035,  9, 24)},
    2036: {'seollal': date(2036,  1, 28), 'buddha': date(2036,  5,  3), 'chuseok': date(2036, 10, 12)},
    2037: {'seollal': date(2037,  2, 15), 'buddha': date(2037,  5, 22), 'chuseok': date(2037, 10,  1)},
    2038: {'seollal': date(2038,  2,  4), 'buddha': date(2038,  5, 11), 'chuseok': date(2038,  9, 21)},
    2039: {'seollal': date(2039,  1, 24), 'buddha': date(2039,  5, 30), 'chuseok': date(2039, 10, 10)},
    2040: {'seollal': date(2040,  2, 12), 'buddha': date(2040,  5, 18), 'chuseok': date(2040,  9, 28)},
}

# 매년 고정 공휴일 (월, 일, 이름) — 대체공휴일 대상
FIXED_HOLIDAYS = [
    (1,  1, '신정'),
    (3,  1, '삼일절'),
    (5,  5, '어린이날'),
    (6,  6, '현충일'),
    (8, 15, '광복절'),
    (10, 3, '개천절'),
    (10, 9, '한글날'),
    (12, 25, '성탄절'),
]


def _all_holiday_dates_for_year(year):
    """해당 연도의 모든 공휴일 날짜와 이름 리스트 반환 (대체공휴일 제외)"""
    holidays = []

    # 고정 공휴일
    for m, d, name in FIXED_HOLIDAYS:
        holidays.append((date(year, m, d), name, 'legal'))

    # 근로자의날
    holidays.append((date(year, 5, 1), '근로자의날', 'legal'))

    # 음력 공휴일
    lunar = LUNAR_DATES.get(year)
    if lunar:
        s = lunar['seollal']
        holidays.append((s - timedelta(days=1), '설날 연휴', 'legal'))
        holidays.append((s,                     '설날',      'legal'))
        holidays.append((s + timedelta(days=1), '설날 연휴', 'legal'))

        holidays.append((lunar['buddha'], '부처님오신날', 'legal'))

        c = lunar['chuseok']
        holidays.append((c - timedelta(days=1), '추석 연휴', 'legal'))
        holidays.append((c,                     '추석',      'legal'))
        holidays.append((c + timedelta(days=1), '추석 연휴', 'legal'))

    return holidays


def _next_workday(d, holiday_dates_set):
    """d 다음 날부터 평일+비공휴일인 첫 날 반환"""
    candidate = d + timedelta(days=1)
    while candidate.weekday() >= 5 or candidate in holiday_dates_set:
        candidate += timedelta(days=1)
    return candidate


def generate_holidays_for_year(year):
    """해당 연도의 음력 공휴일 + 대체공휴일 생성 리스트 반환"""
    base_holidays = _all_holiday_dates_for_year(year)
    base_dates = {h[0] for h in base_holidays}
    result = []

    lunar = LUNAR_DATES.get(year)
    if not lunar:
        return result

    # ── 음력 공휴일 (설날 3일, 부처님오신날, 추석 3일) ──
    s = lunar['seollal']
    seollal_days = [s - timedelta(days=1), s, s + timedelta(days=1)]
    for d in seollal_days:
        label = '설날' if d == s else '설날 연휴'
        result.append({'name': label, 'date': d, 'type': 'legal'})

    result.append({'name': '부처님오신날', 'date': lunar['buddha'], 'type': 'legal'})

    c = lunar['chuseok']
    chuseok_days = [c - timedelta(days=1), c, c + timedelta(days=1)]
    for d in chuseok_days:
        label = '추석' if d == c else '추석 연휴'
        result.append({'name': label, 'date': d, 'type': 'legal'})

    # ── 대체공휴일 계산 ──────────────────────────────────
    all_substitute = []

    # 설날 대체: 3일 중 일요일이거나 고정공휴일과 겹침
    seollal_subs_needed = 0
    for d in seollal_days:
        if d.weekday() == 6:  # 일요일
            seollal_subs_needed += 1
        elif any(date(year, m, dy) == d for m, dy, _ in FIXED_HOLIDAYS):
            seollal_subs_needed += 1
    occupied = base_dates.copy()
    for _ in range(seollal_subs_needed):
        sub = _next_workday(seollal_days[-1], occupied)
        occupied.add(sub)
        all_substitute.append(('설날 대체공휴일', sub))

    # 추석 대체: 3일 중 일요일이거나 고정공휴일과 겹침
    chuseok_subs_needed = 0
    for d in chuseok_days:
        if d.weekday() == 6:  # 일요일
            chuseok_subs_needed += 1
        elif any(date(year, m, dy) == d for m, dy, _ in FIXED_HOLIDAYS):
            chuseok_subs_needed += 1
    for _ in range(chuseok_subs_needed):
        sub = _next_workday(chuseok_days[-1], occupied)
        occupied.add(sub)
        all_substitute.append(('추석 대체공휴일', sub))

    # 부처님오신날 대체: 일요일이면
    bd = lunar['buddha']
    if bd.weekday() == 6:
        sub = _next_workday(bd, occupied)
        occupied.add(sub)
        all_substitute.append(('부처님오신날 대체공휴일', sub))

    # 고정공휴일 대체 (삼일절, 광복절, 개천절, 한글날, 어린이날, 성탄절, 신정)
    # 어린이날: 토·일 대체 / 나머지: 토·일 대체 (2021년 법 개정)
    for m, d, name in FIXED_HOLIDAYS:
        fd = date(year, m, d)
        if fd.weekday() == 5:  # 토요일
            sub = _next_workday(fd, occupied)
            occupied.add(sub)
            all_substitute.append((f'{name} 대체공휴일', sub))
        elif fd.weekday() == 6:  # 일요일
            sub = _next_workday(fd, occupied)
            occupied.add(sub)
            all_substitute.append((f'{name} 대체공휴일', sub))

    for name, d in all_substitute:
        result.append({'name': name, 'date': d, 'type': 'substitute'})

    return result


class Command(BaseCommand):
    help = '음력 공휴일 + 대체공휴일 자동 생성 (2026~2040)'

    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, help='특정 연도만 생성')
        parser.add_argument('--dry-run', action='store_true', help='저장 없이 결과만 출력')

    def handle(self, *args, **options):
        from apps.progress.models import Holiday
        import datetime

        if options['year']:
            years = [options['year']]
        else:
            current_year = datetime.date.today().year
            years = [current_year, current_year + 1]

        dry_run = options['dry_run']
        total_created = 0

        for year in years:
            if year not in LUNAR_DATES:
                self.stdout.write(self.style.WARNING(f'{year}년: 음력 데이터 없음 (지원: 2026~2040)'))
                continue

            holidays = generate_holidays_for_year(year)
            self.stdout.write(f'\n=== {year}년 ({len(holidays)}건) ===')

            for h in sorted(holidays, key=lambda x: x['date']):
                weekday = '월화수목금토일'[h['date'].weekday()]
                self.stdout.write(f"  {h['date']} ({weekday})  {h['name']}  [{h['type']}]")

                if not dry_run:
                    _, is_new = Holiday.objects.get_or_create(
                        specific_date=h['date'],
                        is_recurring=False,
                        defaults={
                            'name': h['name'],
                            'holiday_type': h['type'],
                            'is_active': True,
                        }
                    )
                    if is_new:
                        total_created += 1

        action = '[DRY-RUN] ' if dry_run else ''
        self.stdout.write(self.style.SUCCESS(f'\n{action}완료: {total_created}건 신규 등록'))
