"""
SLA 업무시간 계산 테스트 — Phase 3-1

업무시간 정의: 08:30 ~ 16:30 (월~금, 공휴일 제외)
1일 최대 업무시간: 480분
"""
from datetime import date, time, datetime, timedelta
from django.test import TestCase
from django.utils import timezone


def _kst(year, month, day, hour, minute=0):
    """KST timezone-aware datetime 생성 헬퍼"""
    naive = datetime(year, month, day, hour, minute)
    return timezone.make_aware(naive)


# ─────────────────────────────────────────
# business_hours_elapsed_minutes 테스트
# ─────────────────────────────────────────

class BusinessHoursElapsedTest(TestCase):
    """core.sla_utils.business_hours_elapsed_minutes 단위 테스트"""

    def _calc(self, start, end):
        from core.sla_utils import business_hours_elapsed_minutes
        return business_hours_elapsed_minutes(start, end)

    # ── 기본 케이스 ────────────────────────

    def test_same_day_within_business_hours(self):
        """09:00 ~ 12:00 → 180분"""
        self.assertEqual(self._calc(_kst(2026, 4, 6, 9, 0),
                                    _kst(2026, 4, 6, 12, 0)), 180)

    def test_same_day_full_day(self):
        """08:30 ~ 16:30 → 480분 (하루 전체)"""
        self.assertEqual(self._calc(_kst(2026, 4, 6, 8, 30),
                                    _kst(2026, 4, 6, 16, 30)), 480)

    def test_same_day_half_afternoon(self):
        """12:30 ~ 16:30 → 240분"""
        self.assertEqual(self._calc(_kst(2026, 4, 6, 12, 30),
                                    _kst(2026, 4, 6, 16, 30)), 240)

    # ── 업무시간 경계 클리핑 ──────────────

    def test_start_before_work_start_clips(self):
        """07:00 ~ 10:00 → 90분 (08:30 기준 클리핑)"""
        self.assertEqual(self._calc(_kst(2026, 4, 6, 7, 0),
                                    _kst(2026, 4, 6, 10, 0)), 90)

    def test_end_after_work_end_clips(self):
        """15:00 ~ 18:00 → 90분 (16:30 기준 클리핑)"""
        self.assertEqual(self._calc(_kst(2026, 4, 6, 15, 0),
                                    _kst(2026, 4, 6, 18, 0)), 90)

    def test_start_after_work_end_same_day(self):
        """17:00 ~ 19:00 같은날 → 0분"""
        self.assertEqual(self._calc(_kst(2026, 4, 6, 17, 0),
                                    _kst(2026, 4, 6, 19, 0)), 0)

    def test_start_equals_end(self):
        """동일 시각 → 0분"""
        self.assertEqual(self._calc(_kst(2026, 4, 6, 10, 0),
                                    _kst(2026, 4, 6, 10, 0)), 0)

    def test_end_before_start(self):
        """역순 → 0분"""
        self.assertEqual(self._calc(_kst(2026, 4, 6, 14, 0),
                                    _kst(2026, 4, 6, 9, 0)), 0)

    # ── 주말 제외 ─────────────────────────

    def test_weekend_saturday_excluded(self):
        """토요일(2026-04-04) 09:00 ~ 12:00 → 0분"""
        # 2026-04-04는 토요일
        self.assertEqual(self._calc(_kst(2026, 4, 4, 9, 0),
                                    _kst(2026, 4, 4, 12, 0)), 0)

    def test_weekend_sunday_excluded(self):
        """일요일(2026-04-05) 전체 → 0분"""
        self.assertEqual(self._calc(_kst(2026, 4, 5, 8, 0),
                                    _kst(2026, 4, 5, 18, 0)), 0)

    def test_across_weekend_friday_to_monday(self):
        """금요일 15:00 ~ 월요일 10:00 → 90 + 90 = 180분"""
        # 2026-04-03(금) 15:00 → 2026-04-06(월) 10:00
        result = self._calc(_kst(2026, 4, 3, 15, 0),
                             _kst(2026, 4, 6, 10, 0))
        self.assertEqual(result, 180)  # 90(금) + 90(월)

    def test_across_weekend_full_week(self):
        """월요일 08:30 ~ 금요일 16:30 → 5일 × 480 = 2400분"""
        result = self._calc(_kst(2026, 4, 6, 8, 30),
                             _kst(2026, 4, 10, 16, 30))
        self.assertEqual(result, 2400)

    # ── 이틀 이상 ─────────────────────────

    def test_two_consecutive_business_days(self):
        """월 09:00 ~ 화 11:00 → 450 + 150 = 600분"""
        # 월 09:00 ~ 16:30 = 450분, 화 08:30 ~ 11:00 = 150분
        result = self._calc(_kst(2026, 4, 6, 9, 0),
                             _kst(2026, 4, 7, 11, 0))
        self.assertEqual(result, 600)

    def test_overnight_within_same_business_week(self):
        """수 16:00 ~ 목 09:30 → 30 + 60 = 90분"""
        result = self._calc(_kst(2026, 4, 8, 16, 0),
                             _kst(2026, 4, 9, 9, 30))
        self.assertEqual(result, 90)

    # ── 공휴일 제외 ───────────────────────

    def test_holiday_excluded(self):
        """특정 날짜가 공휴일이면 업무시간 0"""
        from apps.progress.models import Holiday
        # 2026-04-07(화)을 임시 공휴일로 등록
        Holiday.objects.create(
            name='테스트공휴일',
            is_recurring=False,
            specific_date=date(2026, 4, 7),
            is_active=True,
        )
        result = self._calc(_kst(2026, 4, 7, 9, 0),
                             _kst(2026, 4, 7, 12, 0))
        self.assertEqual(result, 0)

    def test_holiday_skipped_across_days(self):
        """월 16:00 ~ (화=공휴일) ~ 수 09:00 → 30 + 0 + 30 = 60분"""
        from apps.progress.models import Holiday
        Holiday.objects.create(
            name='중간공휴일',
            is_recurring=False,
            specific_date=date(2026, 4, 7),
            is_active=True,
        )
        result = self._calc(_kst(2026, 4, 6, 16, 0),
                             _kst(2026, 4, 8, 9, 0))
        self.assertEqual(result, 60)   # 30(월) + 30(수)

    def test_recurring_holiday_excluded(self):
        """매년 반복 공휴일(예: 3/1)은 해당 연도에서 제외"""
        from apps.progress.models import Holiday
        Holiday.objects.create(
            name='삼일절',
            month=3, day=1,
            is_recurring=True,
            is_active=True,
        )
        # 2026-03-02(월) 기준으로 테스트
        result = self._calc(_kst(2026, 3, 2, 9, 0),
                             _kst(2026, 3, 2, 10, 0))
        self.assertEqual(result, 60)   # 공휴일이 아닌 날은 정상 계산

    # ── 업무시간 정확히 시작/종료 ─────────

    def test_starts_exactly_at_work_start(self):
        """08:30 시작 ~ 09:30 → 60분"""
        self.assertEqual(self._calc(_kst(2026, 4, 6, 8, 30),
                                    _kst(2026, 4, 6, 9, 30)), 60)

    def test_ends_exactly_at_work_end(self):
        """15:30 ~ 16:30 → 60분"""
        self.assertEqual(self._calc(_kst(2026, 4, 6, 15, 30),
                                    _kst(2026, 4, 6, 16, 30)), 60)


# ─────────────────────────────────────────
# add_business_hours 테스트
# ─────────────────────────────────────────

class AddBusinessHoursTest(TestCase):
    """core.sla_utils.add_business_hours 단위 테스트"""

    def _add(self, start, hours):
        from core.sla_utils import add_business_hours
        return add_business_hours(start, hours)

    def test_add_1_hour_within_day(self):
        """09:00 + 1h → 10:00"""
        result = self._add(_kst(2026, 4, 6, 9, 0), 1)
        self.assertEqual(result.hour, 10)
        self.assertEqual(result.minute, 0)

    def test_add_8_hours_exactly_fills_day(self):
        """08:30 + 8h → 16:30"""
        result = self._add(_kst(2026, 4, 6, 8, 30), 8)
        self.assertEqual(result.hour, 16)
        self.assertEqual(result.minute, 30)

    def test_add_hours_spanning_next_day(self):
        """14:30 + 4h → 다음 날 10:30 (당일 2h + 익일 2h)"""
        result = self._add(_kst(2026, 4, 6, 14, 30), 4)
        self.assertEqual(result.date(), date(2026, 4, 7))
        self.assertEqual(result.hour, 10)
        self.assertEqual(result.minute, 30)

    def test_add_hours_skips_weekend(self):
        """금요일 15:30 + 2h → 월요일 09:30 (당일 1h + 다음 업무일 1h)"""
        result = self._add(_kst(2026, 4, 3, 15, 30), 2)
        self.assertEqual(result.weekday(), 0)   # 월요일
        self.assertEqual(result.hour, 9)
        self.assertEqual(result.minute, 30)

    def test_add_from_before_work_start(self):
        """07:00 시작 + 1h → 09:30 (08:30 기준 시작)"""
        result = self._add(_kst(2026, 4, 6, 7, 0), 1)
        self.assertEqual(result.hour, 9)
        self.assertEqual(result.minute, 30)

    def test_add_from_after_work_end(self):
        """17:00 시작 + 1h → 다음 업무일 09:30"""
        result = self._add(_kst(2026, 4, 6, 17, 0), 1)
        self.assertEqual(result.date(), date(2026, 4, 7))
        self.assertEqual(result.hour, 9)
        self.assertEqual(result.minute, 30)

    def test_add_zero_hours(self):
        """0시간 추가 → 업무시간 내라면 시작시각 유지"""
        start = _kst(2026, 4, 6, 10, 0)
        result = self._add(start, 0)
        self.assertEqual(result.hour, 10)
        self.assertEqual(result.minute, 0)


# ─────────────────────────────────────────
# SLA 점수 함수 테스트
# ─────────────────────────────────────────

class SLAScoreFunctionsTest(TestCase):
    """core.sla_calculator 개별 점수 함수 경계값 테스트"""

    # ── score_uptime ──────────────────────

    def test_uptime_perfect(self):
        from core.sla_calculator import score_uptime
        self.assertEqual(score_uptime(100.0), 100.0)

    def test_uptime_grade_a_boundary(self):
        from core.sla_calculator import score_uptime
        self.assertEqual(score_uptime(99.98), 100.0)

    def test_uptime_grade_b(self):
        from core.sla_calculator import score_uptime
        self.assertEqual(score_uptime(99.9), 80.0)

    def test_uptime_grade_c(self):
        from core.sla_calculator import score_uptime
        self.assertEqual(score_uptime(99.0), 60.0)

    def test_uptime_grade_d(self):
        from core.sla_calculator import score_uptime
        self.assertEqual(score_uptime(98.5), 40.0)

    def test_uptime_grade_e(self):
        from core.sla_calculator import score_uptime
        self.assertEqual(score_uptime(97.0), 20.0)

    def test_uptime_grade_f(self):
        from core.sla_calculator import score_uptime
        self.assertEqual(score_uptime(96.0), 0.0)

    # ── score_inspection ─────────────────

    def test_inspection_100pct(self):
        from core.sla_calculator import score_inspection
        self.assertEqual(score_inspection(100.0), 100.0)

    def test_inspection_grade_b(self):
        from core.sla_calculator import score_inspection
        self.assertEqual(score_inspection(99.5), 90.0)

    def test_inspection_grade_f(self):
        from core.sla_calculator import score_inspection
        self.assertEqual(score_inspection(96.0), 60.0)

    # ── score_avg_fault_min ───────────────

    def test_avg_fault_min_grade_a(self):
        from core.sla_calculator import score_avg_fault_min
        self.assertEqual(score_avg_fault_min(240), 100.0)

    def test_avg_fault_min_grade_b(self):
        from core.sla_calculator import score_avg_fault_min
        self.assertEqual(score_avg_fault_min(300), 90.0)

    def test_avg_fault_min_grade_c(self):
        from core.sla_calculator import score_avg_fault_min
        self.assertEqual(score_avg_fault_min(400), 80.0)

    def test_avg_fault_min_grade_d(self):
        from core.sla_calculator import score_avg_fault_min
        self.assertEqual(score_avg_fault_min(450), 70.0)

    def test_avg_fault_min_grade_f(self):
        from core.sla_calculator import score_avg_fault_min
        self.assertEqual(score_avg_fault_min(500), 60.0)

    # ── score_fault_count ─────────────────

    def test_fault_count_zero(self):
        from core.sla_calculator import score_fault_count
        self.assertEqual(score_fault_count(0), 100.0)

    def test_fault_count_grade_a_boundary(self):
        from core.sla_calculator import score_fault_count
        self.assertEqual(score_fault_count(5), 100.0)

    def test_fault_count_grade_b(self):
        from core.sla_calculator import score_fault_count
        self.assertEqual(score_fault_count(6), 90.0)

    def test_fault_count_grade_c(self):
        from core.sla_calculator import score_fault_count
        self.assertEqual(score_fault_count(15), 80.0)

    def test_fault_count_grade_f(self):
        from core.sla_calculator import score_fault_count
        self.assertEqual(score_fault_count(31), 60.0)

    # ── score_overtime ───────────────────

    def test_overtime_zero(self):
        from core.sla_calculator import score_overtime
        self.assertEqual(score_overtime(0), 100.0)

    def test_overtime_one(self):
        from core.sla_calculator import score_overtime
        self.assertEqual(score_overtime(1), 80.0)

    def test_overtime_two_plus(self):
        from core.sla_calculator import score_overtime
        self.assertEqual(score_overtime(2), 60.0)
        self.assertEqual(score_overtime(5), 60.0)

    # ── score_human_error ─────────────────

    def test_human_error_zero(self):
        from core.sla_calculator import score_human_error
        self.assertEqual(score_human_error(0), 100.0)

    def test_human_error_one(self):
        from core.sla_calculator import score_human_error
        self.assertEqual(score_human_error(1), 80.0)

    def test_human_error_two_plus(self):
        from core.sla_calculator import score_human_error
        self.assertEqual(score_human_error(3), 60.0)

    # ── score_recurrence ─────────────────

    def test_recurrence_grade_a(self):
        from core.sla_calculator import score_recurrence
        self.assertEqual(score_recurrence(3), 100.0)

    def test_recurrence_grade_c(self):
        from core.sla_calculator import score_recurrence
        self.assertEqual(score_recurrence(4), 80.0)

    def test_recurrence_grade_f(self):
        from core.sla_calculator import score_recurrence
        self.assertEqual(score_recurrence(6), 60.0)

    # ── score_security ───────────────────

    def test_security_zero(self):
        from core.sla_calculator import score_security
        self.assertEqual(score_security(0), 100.0)

    def test_security_one(self):
        from core.sla_calculator import score_security
        self.assertEqual(score_security(1), 80.0)

    def test_security_two_plus(self):
        from core.sla_calculator import score_security
        self.assertEqual(score_security(2), 60.0)

    # ── score_satisfaction ────────────────

    def test_satisfaction_perfect(self):
        from core.sla_calculator import score_satisfaction
        self.assertEqual(score_satisfaction(100.0), 100.0)

    def test_satisfaction_grade_b(self):
        from core.sla_calculator import score_satisfaction
        self.assertEqual(score_satisfaction(99.5), 90.0)

    def test_satisfaction_grade_f(self):
        from core.sla_calculator import score_satisfaction
        self.assertEqual(score_satisfaction(96.9), 60.0)


# ─────────────────────────────────────────
# grade_from_score 테스트
# ─────────────────────────────────────────

class GradeFromScoreTest(TestCase):

    def test_grade_excellent(self):
        from core.sla_calculator import grade_from_score
        self.assertEqual(grade_from_score(95), 'excellent')
        self.assertEqual(grade_from_score(100), 'excellent')

    def test_grade_good(self):
        from core.sla_calculator import grade_from_score
        self.assertEqual(grade_from_score(90), 'good')
        self.assertEqual(grade_from_score(94), 'good')

    def test_grade_normal(self):
        from core.sla_calculator import grade_from_score
        self.assertEqual(grade_from_score(85), 'normal')
        self.assertEqual(grade_from_score(89), 'normal')

    def test_grade_poor(self):
        from core.sla_calculator import grade_from_score
        self.assertEqual(grade_from_score(80), 'poor')
        self.assertEqual(grade_from_score(84), 'poor')

    def test_grade_bad(self):
        from core.sla_calculator import grade_from_score
        self.assertEqual(grade_from_score(79), 'bad')
        self.assertEqual(grade_from_score(0), 'bad')


# ─────────────────────────────────────────
# 업무시간 상수 검증
# ─────────────────────────────────────────

class SLAConstantsTest(TestCase):

    def test_work_start_is_8_30(self):
        from core.sla_utils import WORK_START
        self.assertEqual(WORK_START, time(8, 30))

    def test_work_end_is_16_30(self):
        from core.sla_utils import WORK_END
        self.assertEqual(WORK_END, time(16, 30))

    def test_work_minutes_per_day_is_480(self):
        from core.sla_utils import WORK_MINUTES_PER_DAY
        self.assertEqual(WORK_MINUTES_PER_DAY, 480)
