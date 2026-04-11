"""
SLA 업무시간 계산 유틸리티
- 업무시간: 08:30 ~ 16:30 (월~금, 공휴일 제외)
- 천재지변 등 force majeure는 별도 처리(향후 확장)
"""
from datetime import time, timedelta, datetime
from django.utils import timezone

WORK_START = time(8, 30)
WORK_END   = time(16, 30)
WORK_MINUTES_PER_DAY = 8 * 60  # 480분


def _get_holiday_dates(year: int) -> set:
    """해당 연도의 모든 휴일 날짜 set 반환 (DB 조회)"""
    from apps.progress.models import Holiday
    from datetime import date
    holidays = set()
    for h in Holiday.objects.filter(is_active=True):
        if h.is_recurring and h.month and h.day:
            try:
                holidays.add(date(year, h.month, h.day))
            except ValueError:
                pass
        elif not h.is_recurring and h.specific_date:
            if h.specific_date.year == year:
                holidays.add(h.specific_date)
    return holidays


def _is_business_day(d, holiday_sets: dict) -> bool:
    """주말 또는 휴일이면 False"""
    if d.weekday() >= 5:  # 토(5), 일(6)
        return False
    year = d.year
    if year not in holiday_sets:
        holiday_sets[year] = _get_holiday_dates(year)
    return d not in holiday_sets[year]


def _next_business_day_start(d, holiday_sets: dict):
    """d 다음 업무일 08:30 datetime 반환 (timezone-aware)"""
    from datetime import date
    candidate = d + timedelta(days=1)
    while not _is_business_day(candidate, holiday_sets):
        candidate += timedelta(days=1)
    # received_at 의 tzinfo 를 재사용하기 위해 naive datetime 생성 후 make_aware
    naive = datetime.combine(candidate, WORK_START)
    return timezone.make_aware(naive)


def add_business_hours(start_dt, hours: float):
    """
    start_dt 로부터 업무시간 기준 hours 시간 후 datetime 반환.
    start_dt 가 업무시간 외라면 다음 업무일 08:30 부터 카운트.
    """
    holiday_sets = {}
    remaining = int(hours * 60)  # 분 단위

    # KST 로컬 datetime 으로 통일
    current = timezone.localtime(start_dt)

    # 현재 시각이 업무일이 아니거나 업무시간 외라면 다음 업무일 시작으로 이동
    current_date = current.date()
    current_time = current.time()

    if not _is_business_day(current_date, holiday_sets) or current_time >= WORK_END:
        current = _next_business_day_start(current_date, holiday_sets)
    elif current_time < WORK_START:
        naive = datetime.combine(current_date, WORK_START)
        current = timezone.make_aware(naive)

    while remaining > 0:
        # 오늘 남은 업무시간(분)
        work_end_dt = timezone.make_aware(datetime.combine(current.date(), WORK_END))
        available = int((work_end_dt - current).total_seconds() / 60)

        if remaining <= available:
            current = current + timedelta(minutes=remaining)
            remaining = 0
        else:
            remaining -= available
            current = _next_business_day_start(current.date(), holiday_sets)

    return current


def business_hours_elapsed_minutes(start_dt, end_dt) -> int:
    """
    start_dt ~ end_dt 사이 실제 업무시간(분) 반환.
    """
    holiday_sets = {}
    start = timezone.localtime(start_dt)
    end   = timezone.localtime(end_dt)

    if end <= start:
        return 0

    total = 0
    current = start

    while current.date() <= end.date():
        d = current.date()
        if _is_business_day(d, holiday_sets):
            day_start = timezone.make_aware(datetime.combine(d, WORK_START))
            day_end   = timezone.make_aware(datetime.combine(d, WORK_END))

            period_start = max(current, day_start)
            period_end   = min(end, day_end)

            if period_end > period_start:
                total += int((period_end - period_start).total_seconds() / 60)

        # 다음 날 00:00 으로 이동
        from datetime import date as _date
        next_day = d + timedelta(days=1)
        current  = timezone.make_aware(datetime.combine(next_day, time(0, 0)))

    return total
