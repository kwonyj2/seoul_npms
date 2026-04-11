"""
Phase 5-2: 통계/리포트 고도화 + 장애 패턴 분석 테스트

테스트 범위:
  1. aggregate_daily()    — 일별 통계 자동 집계
  2. aggregate_monthly()  — 월별 통계 자동 집계 (지원청별)
  3. IncidentPatternAnalyzer.hourly_distribution   — 시간대별 분포
  4. IncidentPatternAnalyzer.weekday_distribution  — 요일별 분포
  5. IncidentPatternAnalyzer.category_trend        — 카테고리별 추이
  6. IncidentPatternAnalyzer.recurrence_hotspots   — 재발 다발 학교/카테고리
  7. IncidentPatternAnalyzer.school_risk_score     — 학교별 위험도 점수
  8. PerformanceAnalyzer.worker_performance        — 인력별 SLA/처리 성과
  9. /api/statistics/pattern/ API                  — 패턴 분석 API
 10. /api/statistics/daily/aggregate/ API          — 일별 집계 트리거
"""
from decimal import Decimal
from datetime import date, datetime, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.schools.models import SupportCenter, SchoolType, School
from apps.incidents.models import (
    Incident, IncidentCategory, IncidentAssignment,
)
from apps.statistics.models import StatisticsDaily, StatisticsMonthly, SLARecord


# ─────────────────────────────────────────────────────────────
# 공통 픽스처
# ─────────────────────────────────────────────────────────────
class StatFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.center = SupportCenter.objects.create(
            code='east', name='동부교육지원청',
            lat=Decimal('37.5'), lng=Decimal('127.0'),
        )
        cls.center2 = SupportCenter.objects.create(
            code='west', name='서부교육지원청',
            lat=Decimal('37.5'), lng=Decimal('126.9'),
        )
        cls.school_type = SchoolType.objects.create(code='elem', name='초등학교')
        cls.school = School.objects.create(
            support_center=cls.center, school_type=cls.school_type,
            name='테스트초등', address='서울',
        )
        cls.school2 = School.objects.create(
            support_center=cls.center2, school_type=cls.school_type,
            name='서부초등', address='서울',
        )
        cls.cat_wired = IncidentCategory.objects.create(
            code='wired', name='유선망', order=1
        )
        cls.cat_wifi = IncidentCategory.objects.create(
            code='wifi', name='무선망', order=2
        )
        cls.admin = User.objects.create_user(
            username='stat_admin', email='stat_admin@test.com',
            password='pass', role='admin',
            support_center=cls.center,
        )
        cls.worker = User.objects.create_user(
            username='stat_worker', email='stat_worker@test.com',
            password='pass', role='worker',
            support_center=cls.center,
        )

    def _make_incident(self, school=None, category=None, status='completed',
                       priority='medium', received_offset_hours=0,
                       arrival_minutes=30, resolve_minutes=120):
        """테스트용 완료 장애 생성"""
        school = school or self.school
        category = category or self.cat_wired
        now = timezone.now()
        received_at = now - timedelta(hours=received_offset_hours + 2)
        arrived_at = received_at + timedelta(minutes=arrival_minutes)
        completed_at = received_at + timedelta(minutes=resolve_minutes)
        inc = Incident.objects.create(
            incident_number=Incident.generate_number(),
            school=school,
            category=category,
            status=status,
            priority=priority,
            received_by=self.admin,
            requester_name='요청자',
            requester_phone='010-1234-5678',
            description='테스트 장애',
            received_at=received_at,
            arrived_at=arrived_at if status == 'completed' else None,
            completed_at=completed_at if status == 'completed' else None,
            sla_arrival_ok=arrival_minutes <= 60,
            sla_resolve_ok=resolve_minutes <= 240,
        )
        return inc


# ─────────────────────────────────────────────────────────────
# 1~2. aggregate_daily / aggregate_monthly
# ─────────────────────────────────────────────────────────────
class AggregateDailyTest(StatFixtureMixin, TestCase):
    """aggregate_daily(target_date) — 일별 통계 집계"""

    def setUp(self):
        self._make_incident(status='completed', arrival_minutes=30, resolve_minutes=120)
        self._make_incident(status='completed', arrival_minutes=90, resolve_minutes=300)  # SLA 위반
        self._make_incident(status='received')

    def test_creates_statistics_daily_record(self):
        from apps.statistics.services import aggregate_daily
        target = date.today()
        aggregate_daily(target)
        self.assertTrue(StatisticsDaily.objects.filter(stat_date=target).exists())

    def test_total_incidents_counted(self):
        from apps.statistics.services import aggregate_daily
        target = date.today()
        aggregate_daily(target)
        stat = StatisticsDaily.objects.get(stat_date=target)
        self.assertGreaterEqual(stat.total_incidents, 3)

    def test_completed_incidents_counted(self):
        from apps.statistics.services import aggregate_daily
        target = date.today()
        aggregate_daily(target)
        stat = StatisticsDaily.objects.get(stat_date=target)
        self.assertGreaterEqual(stat.completed_incidents, 2)

    def test_sla_arrival_ok_counted(self):
        """도착 SLA 준수 건수 집계"""
        from apps.statistics.services import aggregate_daily
        target = date.today()
        aggregate_daily(target)
        stat = StatisticsDaily.objects.get(stat_date=target)
        # arrival_minutes=30인 장애 1건이 SLA OK
        self.assertGreaterEqual(stat.sla_arrival_ok, 1)

    def test_idempotent_update(self):
        """동일 날짜 재집계 시 update_or_create (중복 생성 없음)"""
        from apps.statistics.services import aggregate_daily
        target = date.today()
        aggregate_daily(target)
        aggregate_daily(target)
        count = StatisticsDaily.objects.filter(stat_date=target).count()
        self.assertEqual(count, 1)

    def test_avg_arrival_min_calculated(self):
        """평균 도착 시간(분) 계산"""
        from apps.statistics.services import aggregate_daily
        target = date.today()
        aggregate_daily(target)
        stat = StatisticsDaily.objects.get(stat_date=target)
        # 완료 장애가 있으면 avg_arrival_min이 None이 아니어야 함
        self.assertIsNotNone(stat.avg_arrival_min)


class AggregateMonthlyTest(StatFixtureMixin, TestCase):
    """aggregate_monthly(year, month) — 월별 통계 집계 (지원청별)"""

    def setUp(self):
        self._make_incident(school=self.school, status='completed')
        self._make_incident(school=self.school2, status='completed', arrival_minutes=90)

    def test_creates_monthly_records(self):
        from apps.statistics.services import aggregate_monthly
        now = timezone.now()
        aggregate_monthly(now.year, now.month)
        self.assertTrue(StatisticsMonthly.objects.filter(
            year=now.year, month=now.month
        ).exists())

    def test_per_center_records_created(self):
        """지원청별 레코드가 각각 생성된다"""
        from apps.statistics.services import aggregate_monthly
        now = timezone.now()
        aggregate_monthly(now.year, now.month)
        self.assertTrue(StatisticsMonthly.objects.filter(
            year=now.year, month=now.month, support_center=self.center
        ).exists())
        self.assertTrue(StatisticsMonthly.objects.filter(
            year=now.year, month=now.month, support_center=self.center2
        ).exists())

    def test_sla_arrival_rate_is_percentage(self):
        """SLA 도착 준수율이 0~100 범위"""
        from apps.statistics.services import aggregate_monthly
        now = timezone.now()
        aggregate_monthly(now.year, now.month)
        for rec in StatisticsMonthly.objects.filter(year=now.year, month=now.month):
            self.assertGreaterEqual(rec.sla_arrival_rate, 0)
            self.assertLessEqual(rec.sla_arrival_rate, 100)

    def test_idempotent_update(self):
        """동일 연월 재집계 시 중복 생성 없음"""
        from apps.statistics.services import aggregate_monthly
        now = timezone.now()
        aggregate_monthly(now.year, now.month)
        aggregate_monthly(now.year, now.month)
        count = StatisticsMonthly.objects.filter(
            year=now.year, month=now.month, support_center=self.center
        ).count()
        self.assertEqual(count, 1)


# ─────────────────────────────────────────────────────────────
# 3~7. IncidentPatternAnalyzer
# ─────────────────────────────────────────────────────────────
class HourlyDistributionTest(StatFixtureMixin, TestCase):
    """시간대별 장애 분포"""

    def setUp(self):
        # 로컬 오전 9시에 접수된 장애 3건 (localtime 기준으로 설정)
        local_9am = timezone.localtime(timezone.now()).replace(hour=9, minute=0, second=0, microsecond=0)
        for i in range(3):
            inc = self._make_incident()
            inc.received_at = local_9am
            inc.save(update_fields=['received_at'])
        # 로컬 오후 14시 장애 1건
        local_2pm = timezone.localtime(timezone.now()).replace(hour=14, minute=0, second=0, microsecond=0)
        inc = self._make_incident()
        inc.received_at = local_2pm
        inc.save(update_fields=['received_at'])

    def test_returns_24_hour_buckets(self):
        from apps.statistics.services import IncidentPatternAnalyzer
        qs = Incident.objects.filter(school__support_center=self.center)
        result = IncidentPatternAnalyzer.hourly_distribution(qs)
        self.assertEqual(len(result), 24)

    def test_peak_hour_detected(self):
        """9시가 최다 발생 시간대"""
        from apps.statistics.services import IncidentPatternAnalyzer
        qs = Incident.objects.filter(school__support_center=self.center)
        result = IncidentPatternAnalyzer.hourly_distribution(qs)
        peak = max(result, key=lambda x: x['count'])
        self.assertEqual(peak['hour'], 9)

    def test_all_hours_present(self):
        """0~23시 모두 포함되어야 함"""
        from apps.statistics.services import IncidentPatternAnalyzer
        qs = Incident.objects.all()
        result = IncidentPatternAnalyzer.hourly_distribution(qs)
        hours = [r['hour'] for r in result]
        self.assertEqual(hours, list(range(24)))


class WeekdayDistributionTest(StatFixtureMixin, TestCase):
    """요일별 장애 분포"""

    def setUp(self):
        # 월요일(weekday=0)에 접수된 장애 2건
        monday = date(2026, 4, 6)  # 2026-04-06 is Monday
        dt = timezone.make_aware(datetime.combine(monday, datetime.min.time().replace(hour=10)))
        for i in range(2):
            inc = self._make_incident()
            inc.received_at = dt
            inc.save(update_fields=['received_at'])

    def test_returns_7_weekday_buckets(self):
        from apps.statistics.services import IncidentPatternAnalyzer
        qs = Incident.objects.all()
        result = IncidentPatternAnalyzer.weekday_distribution(qs)
        self.assertEqual(len(result), 7)

    def test_weekday_keys_present(self):
        """0(월)~6(일) 키 존재"""
        from apps.statistics.services import IncidentPatternAnalyzer
        qs = Incident.objects.all()
        result = IncidentPatternAnalyzer.weekday_distribution(qs)
        weekdays = [r['weekday'] for r in result]
        self.assertEqual(weekdays, list(range(7)))

    def test_monday_has_highest_count(self):
        from apps.statistics.services import IncidentPatternAnalyzer
        qs = Incident.objects.all()
        result = IncidentPatternAnalyzer.weekday_distribution(qs)
        mon = next(r for r in result if r['weekday'] == 0)
        others = [r for r in result if r['weekday'] != 0]
        self.assertGreater(mon['count'], max(r['count'] for r in others) if others else 0)


class CategoryTrendTest(StatFixtureMixin, TestCase):
    """카테고리별 월별 추이"""

    def setUp(self):
        now = timezone.now()
        for i in range(3):
            self._make_incident(category=self.cat_wired)
        for i in range(1):
            self._make_incident(category=self.cat_wifi)

    def test_returns_list_of_category_counts(self):
        from apps.statistics.services import IncidentPatternAnalyzer
        now = timezone.now()
        result = IncidentPatternAnalyzer.category_trend(now.year, now.month)
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_result_has_required_keys(self):
        from apps.statistics.services import IncidentPatternAnalyzer
        now = timezone.now()
        result = IncidentPatternAnalyzer.category_trend(now.year, now.month)
        if result:
            row = result[0]
            for k in ('category', 'count'):
                self.assertIn(k, row)

    def test_wired_is_top_category(self):
        """유선망 3건 > 무선망 1건"""
        from apps.statistics.services import IncidentPatternAnalyzer
        now = timezone.now()
        result = IncidentPatternAnalyzer.category_trend(now.year, now.month)
        top = result[0]
        self.assertEqual(top['category'], '유선망')


class RecurrenceHotspotsTest(StatFixtureMixin, TestCase):
    """재발 다발 학교/카테고리 분석"""

    def setUp(self):
        # 같은 학교+카테고리 재발 5건
        for i in range(5):
            self._make_incident(school=self.school, category=self.cat_wired)
        # 다른 학교 1건
        self._make_incident(school=self.school2, category=self.cat_wifi)

    def test_returns_list(self):
        from apps.statistics.services import IncidentPatternAnalyzer
        result = IncidentPatternAnalyzer.recurrence_hotspots(
            center=self.center, top_n=5
        )
        self.assertIsInstance(result, list)

    def test_hotspot_school_appears_first(self):
        """다발 학교가 첫 번째"""
        from apps.statistics.services import IncidentPatternAnalyzer
        result = IncidentPatternAnalyzer.recurrence_hotspots(
            center=self.center, top_n=5
        )
        self.assertGreater(len(result), 0)
        top = result[0]
        self.assertIn('school', top)
        self.assertIn('count', top)

    def test_top_n_limit_respected(self):
        from apps.statistics.services import IncidentPatternAnalyzer
        result = IncidentPatternAnalyzer.recurrence_hotspots(
            center=self.center, top_n=2
        )
        self.assertLessEqual(len(result), 2)

    def test_center_filter_works(self):
        """다른 지원청 학교는 제외"""
        from apps.statistics.services import IncidentPatternAnalyzer
        result = IncidentPatternAnalyzer.recurrence_hotspots(
            center=self.center2, top_n=5
        )
        school_names = [r['school'] for r in result]
        self.assertNotIn(self.school.name, school_names)


class SchoolRiskScoreTest(StatFixtureMixin, TestCase):
    """학교별 위험도 점수 계산"""

    def setUp(self):
        # school: 고위험 (5건, 높은 우선순위)
        for i in range(5):
            self._make_incident(school=self.school, priority='critical')
        # school2: 저위험 (1건)
        self._make_incident(school=self.school2, priority='low')

    def test_returns_list_with_score(self):
        from apps.statistics.services import IncidentPatternAnalyzer
        result = IncidentPatternAnalyzer.school_risk_score(center=self.center)
        self.assertIsInstance(result, list)
        if result:
            self.assertIn('school', result[0])
            self.assertIn('risk_score', result[0])

    def test_high_incident_school_has_higher_risk(self):
        """장애 많은 학교가 높은 위험도"""
        from apps.statistics.services import IncidentPatternAnalyzer
        result = IncidentPatternAnalyzer.school_risk_score(center=self.center)
        self.assertGreater(len(result), 0)
        # school이 가장 높은 위험도여야 함
        top = result[0]
        self.assertEqual(top['school'], self.school.name)

    def test_risk_score_is_positive_number(self):
        from apps.statistics.services import IncidentPatternAnalyzer
        result = IncidentPatternAnalyzer.school_risk_score(center=self.center)
        for row in result:
            self.assertGreaterEqual(row['risk_score'], 0)


# ─────────────────────────────────────────────────────────────
# 8. PerformanceAnalyzer — 인력 성과 분석
# ─────────────────────────────────────────────────────────────
class WorkerPerformanceTest(StatFixtureMixin, TestCase):
    """인력별 SLA 준수율 / 처리 시간 분석"""

    def setUp(self):
        # worker에게 완료 장애 3건 배정 (2건 SLA OK, 1건 위반)
        for arrival, resolve, sla_ok in [(30, 120, True), (30, 100, True), (90, 300, False)]:
            inc = self._make_incident(arrival_minutes=arrival, resolve_minutes=resolve)
            inc.sla_arrival_ok = sla_ok
            inc.save(update_fields=['sla_arrival_ok'])
            IncidentAssignment.objects.create(
                incident=inc, worker=self.worker, assigned_by=self.admin
            )

    def test_returns_per_worker_stats(self):
        from apps.statistics.services import PerformanceAnalyzer
        from django.utils import timezone
        start = timezone.now() - timedelta(days=1)
        end = timezone.now()
        result = PerformanceAnalyzer.worker_performance(
            workers=User.objects.filter(pk=self.worker.pk),
            start=start, end=end,
        )
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)

    def test_result_has_required_keys(self):
        from apps.statistics.services import PerformanceAnalyzer
        from django.utils import timezone
        start = timezone.now() - timedelta(days=1)
        end = timezone.now()
        result = PerformanceAnalyzer.worker_performance(
            workers=User.objects.filter(pk=self.worker.pk),
            start=start, end=end,
        )
        row = result[0]
        for k in ('worker', 'total_assigned', 'sla_arrival_rate', 'avg_resolve_min'):
            self.assertIn(k, row)

    def test_sla_arrival_rate_is_percentage(self):
        from apps.statistics.services import PerformanceAnalyzer
        from django.utils import timezone
        start = timezone.now() - timedelta(days=1)
        end = timezone.now()
        result = PerformanceAnalyzer.worker_performance(
            workers=User.objects.filter(pk=self.worker.pk),
            start=start, end=end,
        )
        rate = result[0]['sla_arrival_rate']
        self.assertGreaterEqual(rate, 0)
        self.assertLessEqual(rate, 100)

    def test_total_assigned_correct(self):
        from apps.statistics.services import PerformanceAnalyzer
        from django.utils import timezone
        start = timezone.now() - timedelta(days=1)
        end = timezone.now()
        result = PerformanceAnalyzer.worker_performance(
            workers=User.objects.filter(pk=self.worker.pk),
            start=start, end=end,
        )
        self.assertEqual(result[0]['total_assigned'], 3)


# ─────────────────────────────────────────────────────────────
# 9. /api/statistics/pattern/ API
# ─────────────────────────────────────────────────────────────
class PatternAPITest(StatFixtureMixin, TestCase):
    """장애 패턴 분석 API"""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        for i in range(3):
            self._make_incident()

    def test_pattern_api_returns_200(self):
        resp = self.client.get('/api/statistics/pattern/')
        self.assertEqual(resp.status_code, 200)

    def test_pattern_api_has_hourly(self):
        resp = self.client.get('/api/statistics/pattern/')
        data = resp.json()
        self.assertIn('hourly', data)

    def test_pattern_api_has_weekday(self):
        resp = self.client.get('/api/statistics/pattern/')
        data = resp.json()
        self.assertIn('weekday', data)

    def test_pattern_api_has_category_trend(self):
        resp = self.client.get('/api/statistics/pattern/')
        data = resp.json()
        self.assertIn('category_trend', data)

    def test_pattern_api_has_hotspots(self):
        resp = self.client.get('/api/statistics/pattern/')
        data = resp.json()
        self.assertIn('hotspots', data)

    def test_pattern_api_requires_auth(self):
        c = APIClient()
        resp = c.get('/api/statistics/pattern/')
        self.assertIn(resp.status_code, [401, 403])

    def test_pattern_api_center_filter(self):
        """center 파라미터로 지원청 필터링"""
        resp = self.client.get(f'/api/statistics/pattern/?center={self.center.pk}')
        self.assertEqual(resp.status_code, 200)


# ─────────────────────────────────────────────────────────────
# 10. /api/statistics/daily/aggregate/ API
# ─────────────────────────────────────────────────────────────
class DailyAggregateAPITest(StatFixtureMixin, TestCase):
    """일별 집계 트리거 API (admin 전용)"""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_aggregate_today_returns_200(self):
        resp = self.client.post('/api/statistics/daily/aggregate/')
        self.assertEqual(resp.status_code, 200)

    def test_aggregate_creates_record(self):
        self.client.post('/api/statistics/daily/aggregate/')
        self.assertTrue(StatisticsDaily.objects.filter(stat_date=date.today()).exists())

    def test_aggregate_specific_date(self):
        resp = self.client.post(
            '/api/statistics/daily/aggregate/',
            {'date': '2026-04-01'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(StatisticsDaily.objects.filter(stat_date=date(2026, 4, 1)).exists())

    def test_aggregate_requires_admin(self):
        worker_client = APIClient()
        worker_client.force_authenticate(self.worker)
        resp = worker_client.post('/api/statistics/daily/aggregate/')
        self.assertIn(resp.status_code, [403, 401])
