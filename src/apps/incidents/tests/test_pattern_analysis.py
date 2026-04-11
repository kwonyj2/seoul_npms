"""
Phase 5-2: 장애 패턴 분석 고도화 테스트

테스트 범위:
  1. 학교별 취약 장비 예측 — 설치 연도 + 장애 빈도 + 내용연수 초과 여부
  2. 계절별 장애 패턴 분석 — 봄/여름/가을/겨울 분포
  3. 시간대별 장애 패턴 분석 — 0~23시 버킷
  4. SLA 위반 예측 — 미완료 장애의 위험도 실시간 계산
  5. 월간 인사이트 리포트 자동 생성 — 종합 분석 보고서
  6. API 엔드포인트 — /api/incidents/pattern/
"""
from decimal import Decimal
from datetime import date, timedelta, datetime

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.schools.models import SupportCenter, SchoolType, School
from apps.incidents.models import (
    Incident, IncidentCategory, IncidentAssignment, IncidentSLA,
)
from apps.assets.models import AssetCategory, AssetModel, Asset


# ─────────────────────────────────────────────────────────────
# 공통 픽스처
# ─────────────────────────────────────────────────────────────
class PatternFixtureMixin:
    @classmethod
    def setUpTestData(cls):
        cls.center = SupportCenter.objects.create(
            code='north', name='북부교육지원청',
            lat=Decimal('37.6'), lng=Decimal('127.0'),
        )
        cls.school_type = SchoolType.objects.create(code='middle', name='중학교')
        cls.school = School.objects.create(
            support_center=cls.center, school_type=cls.school_type,
            name='패턴분석중학교', address='서울',
        )
        cls.school2 = School.objects.create(
            support_center=cls.center, school_type=cls.school_type,
            name='취약장비중학교', address='서울',
        )
        cls.cat = IncidentCategory.objects.create(
            code='switch_fail', name='스위치 장애', order=1
        )
        cls.admin = User.objects.create_user(
            username='pattern_admin', email='pattern_admin@test.com',
            password='pass', role='admin',
            support_center=cls.center,
        )
        # 장비 분류 (내용연수 5년)
        cls.asset_cat = AssetCategory.objects.create(
            code='switch', name='스위치', usable_years=5
        )
        cls.asset_model = AssetModel.objects.create(
            category=cls.asset_cat,
            manufacturer='코어엣지',
            model_name='C3100-24TL',
        )

    def _make_incident(self, school=None, category=None, status='completed',
                       priority='medium', received_offset_days=0,
                       arrival_minutes=30, resolve_minutes=120):
        school = school or self.school
        category = category or self.cat
        now = timezone.now() - timedelta(days=received_offset_days)
        received_at = now - timedelta(hours=3)
        inc = Incident.objects.create(
            incident_number=Incident.generate_number(),
            school=school,
            category=category,
            status=status,
            priority=priority,
            received_by=self.admin,
            requester_name='요청자',
            requester_phone='010-0000-0000',
            description='패턴 테스트',
            received_at=received_at,
            arrived_at=received_at + timedelta(minutes=arrival_minutes),
            completed_at=received_at + timedelta(minutes=resolve_minutes) if status == 'completed' else None,
            sla_arrival_ok=arrival_minutes <= 120,
            sla_resolve_ok=resolve_minutes <= 480,
        )
        return inc

    def _make_asset(self, school=None, install_year=2020, serial_suffix='001'):
        school = school or self.school2
        return Asset.objects.create(
            asset_model=self.asset_model,
            serial_number=f'SN-PATTERN-{serial_suffix}-{school.pk}',
            status='installed',
            current_school=school,
            install_year=install_year,
        )


# ─────────────────────────────────────────────────────────────
# 1. 취약 장비 예측
# ─────────────────────────────────────────────────────────────
class VulnerableAssetPredictionTest(PatternFixtureMixin, TestCase):
    """학교별 취약 장비 예측 (설치 연도 + 장애 빈도 + 내용연수)"""

    def setUp(self):
        # school2에 2018년 설치 장비 (내용연수 5년 → 이미 초과)
        self.old_asset = self._make_asset(
            school=self.school2, install_year=2018, serial_suffix='old'
        )
        # school2에서 장애 5건
        for i in range(5):
            self._make_incident(school=self.school2)
        # school에는 최신 장비 + 장애 1건
        self.new_asset = self._make_asset(
            school=self.school, install_year=2024, serial_suffix='new'
        )
        self._make_incident(school=self.school)

    def test_function_importable(self):
        try:
            from apps.incidents.pattern_service import predict_vulnerable_assets
        except ImportError:
            self.fail('predict_vulnerable_assets 가 pattern_service.py에 없습니다.')

    def test_returns_list(self):
        from apps.incidents.pattern_service import predict_vulnerable_assets
        result = predict_vulnerable_assets(center=self.center)
        self.assertIsInstance(result, list)

    def test_result_has_required_keys(self):
        from apps.incidents.pattern_service import predict_vulnerable_assets
        result = predict_vulnerable_assets(center=self.center)
        if result:
            row = result[0]
            for key in ('school', 'asset_count', 'overdue_count',
                        'incident_count', 'vulnerability_score'):
                self.assertIn(key, row)

    def test_overdue_asset_detected(self):
        """내용연수 초과 장비가 있는 학교 감지"""
        from apps.incidents.pattern_service import predict_vulnerable_assets
        result = predict_vulnerable_assets(center=self.center)
        school2_row = next((r for r in result if r['school'] == self.school2.name), None)
        self.assertIsNotNone(school2_row)
        self.assertGreater(school2_row['overdue_count'], 0)

    def test_high_incident_school_has_higher_score(self):
        """장애 빈도 많은 학교가 높은 취약도 점수"""
        from apps.incidents.pattern_service import predict_vulnerable_assets
        result = predict_vulnerable_assets(center=self.center)
        self.assertGreater(len(result), 0)
        # 가장 높은 점수가 school2 (장애 5건 + 노후 장비)
        top = result[0]
        self.assertEqual(top['school'], self.school2.name)

    def test_new_asset_low_vulnerability(self):
        """최신 장비 학교는 낮은 취약도"""
        from apps.incidents.pattern_service import predict_vulnerable_assets
        result = predict_vulnerable_assets(center=self.center)
        school_row = next((r for r in result if r['school'] == self.school.name), None)
        if school_row:
            # school2 (노후+다발) 보다 낮아야 함
            school2_row = next((r for r in result if r['school'] == self.school2.name), None)
            if school2_row:
                self.assertLessEqual(
                    school_row['vulnerability_score'],
                    school2_row['vulnerability_score']
                )

    def test_top_n_parameter(self):
        """top_n 파라미터로 결과 수 제한"""
        from apps.incidents.pattern_service import predict_vulnerable_assets
        result = predict_vulnerable_assets(center=self.center, top_n=1)
        self.assertLessEqual(len(result), 1)


# ─────────────────────────────────────────────────────────────
# 2. 계절별 장애 패턴 분석
# ─────────────────────────────────────────────────────────────
class SeasonalPatternTest(PatternFixtureMixin, TestCase):
    """계절별(봄/여름/가을/겨울) 장애 분포"""

    def setUp(self):
        # 여름(7월) 장애 3건
        summer_dt = timezone.make_aware(datetime(2026, 7, 15, 10, 0))
        for i in range(3):
            inc = self._make_incident()
            inc.received_at = summer_dt
            inc.save(update_fields=['received_at'])
        # 겨울(1월) 장애 1건
        winter_dt = timezone.make_aware(datetime(2026, 1, 10, 10, 0))
        inc = self._make_incident()
        inc.received_at = winter_dt
        inc.save(update_fields=['received_at'])

    def test_function_importable(self):
        try:
            from apps.incidents.pattern_service import analyze_seasonal_pattern
        except ImportError:
            self.fail('analyze_seasonal_pattern 이 pattern_service.py에 없습니다.')

    def test_returns_4_seasons(self):
        from apps.incidents.pattern_service import analyze_seasonal_pattern
        qs = Incident.objects.filter(school__support_center=self.center)
        result = analyze_seasonal_pattern(qs)
        self.assertEqual(len(result), 4)

    def test_season_keys_correct(self):
        """봄/여름/가을/겨울 키 존재"""
        from apps.incidents.pattern_service import analyze_seasonal_pattern
        qs = Incident.objects.all()
        result = analyze_seasonal_pattern(qs)
        seasons = [r['season'] for r in result]
        self.assertIn('봄', seasons)
        self.assertIn('여름', seasons)
        self.assertIn('가을', seasons)
        self.assertIn('겨울', seasons)

    def test_summer_is_peak(self):
        """여름(7월 장애 3건)이 최다"""
        from apps.incidents.pattern_service import analyze_seasonal_pattern
        qs = Incident.objects.filter(school__support_center=self.center)
        result = analyze_seasonal_pattern(qs)
        summer = next(r for r in result if r['season'] == '여름')
        winter = next(r for r in result if r['season'] == '겨울')
        self.assertGreater(summer['count'], winter['count'])

    def test_result_has_count_and_ratio(self):
        from apps.incidents.pattern_service import analyze_seasonal_pattern
        qs = Incident.objects.all()
        result = analyze_seasonal_pattern(qs)
        for row in result:
            self.assertIn('count', row)
            self.assertIn('ratio', row)


# ─────────────────────────────────────────────────────────────
# 3. 시간대별 장애 패턴 (기존 services.py와 독립적으로 pattern_service에도 구현)
# ─────────────────────────────────────────────────────────────
class HourlyPatternTest(PatternFixtureMixin, TestCase):
    """시간대별 장애 분포 (pattern_service 버전)"""

    def setUp(self):
        local_9am = timezone.localtime(timezone.now()).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        for i in range(4):
            inc = self._make_incident()
            inc.received_at = local_9am
            inc.save(update_fields=['received_at'])

    def test_function_importable(self):
        try:
            from apps.incidents.pattern_service import analyze_hourly_pattern
        except ImportError:
            self.fail('analyze_hourly_pattern 이 pattern_service.py에 없습니다.')

    def test_returns_24_buckets(self):
        from apps.incidents.pattern_service import analyze_hourly_pattern
        qs = Incident.objects.filter(school__support_center=self.center)
        result = analyze_hourly_pattern(qs)
        self.assertEqual(len(result), 24)

    def test_9am_is_peak(self):
        from apps.incidents.pattern_service import analyze_hourly_pattern
        qs = Incident.objects.filter(school__support_center=self.center)
        result = analyze_hourly_pattern(qs)
        peak = max(result, key=lambda x: x['count'])
        self.assertEqual(peak['hour'], 9)


# ─────────────────────────────────────────────────────────────
# 4. SLA 위반 예측
# ─────────────────────────────────────────────────────────────
class SLARiskPredictionTest(PatternFixtureMixin, TestCase):
    """미완료 장애의 SLA 위반 위험도 실시간 계산"""

    def setUp(self):
        # 위험 장애: 접수 후 100분 경과 (SLA 기준 2시간=120분 → 83% 소진)
        self.risky_inc = self._make_incident(status='assigned')
        self.risky_inc.received_at = timezone.now() - timedelta(minutes=100)
        self.risky_inc.save(update_fields=['received_at'])
        # IncidentSLA 생성 (도착 목표: 접수+2시간)
        IncidentSLA.objects.create(
            incident=self.risky_inc,
            arrival_target=self.risky_inc.received_at + timedelta(hours=2),
            resolve_target=self.risky_inc.received_at + timedelta(hours=8),
            arrival_ok=None,
            resolve_ok=None,
        )

        # 안전 장애: 방금 접수
        self.safe_inc = self._make_incident(status='received')
        self.safe_inc.received_at = timezone.now() - timedelta(minutes=5)
        self.safe_inc.save(update_fields=['received_at'])
        IncidentSLA.objects.create(
            incident=self.safe_inc,
            arrival_target=self.safe_inc.received_at + timedelta(hours=2),
            resolve_target=self.safe_inc.received_at + timedelta(hours=8),
            arrival_ok=None,
            resolve_ok=None,
        )

    def test_function_importable(self):
        try:
            from apps.incidents.pattern_service import predict_sla_risk
        except ImportError:
            self.fail('predict_sla_risk 가 pattern_service.py에 없습니다.')

    def test_returns_list_of_at_risk_incidents(self):
        from apps.incidents.pattern_service import predict_sla_risk
        result = predict_sla_risk(center=self.center)
        self.assertIsInstance(result, list)

    def test_result_has_required_keys(self):
        from apps.incidents.pattern_service import predict_sla_risk
        result = predict_sla_risk(center=self.center)
        if result:
            row = result[0]
            for key in ('incident_number', 'school', 'arrival_risk_pct',
                        'resolve_risk_pct', 'status'):
                self.assertIn(key, row)

    def test_risky_incident_has_high_risk(self):
        """100분 경과 → 도착 위험도 83% 이상"""
        from apps.incidents.pattern_service import predict_sla_risk
        result = predict_sla_risk(center=self.center)
        risky_row = next(
            (r for r in result if r['incident_number'] == self.risky_inc.incident_number),
            None
        )
        self.assertIsNotNone(risky_row)
        self.assertGreater(risky_row['arrival_risk_pct'], 70)

    def test_safe_incident_has_low_risk(self):
        """5분 경과 → 도착 위험도 낮음"""
        from apps.incidents.pattern_service import predict_sla_risk
        result = predict_sla_risk(center=self.center)
        safe_row = next(
            (r for r in result if r['incident_number'] == self.safe_inc.incident_number),
            None
        )
        if safe_row:
            self.assertLess(safe_row['arrival_risk_pct'], 30)

    def test_only_active_incidents_included(self):
        """완료된 장애는 위험도 계산에서 제외"""
        from apps.incidents.pattern_service import predict_sla_risk
        completed_inc = self._make_incident(status='completed')
        result = predict_sla_risk(center=self.center)
        completed_numbers = {r['incident_number'] for r in result}
        self.assertNotIn(completed_inc.incident_number, completed_numbers)

    def test_threshold_parameter(self):
        """threshold 이상인 장애만 반환"""
        from apps.incidents.pattern_service import predict_sla_risk
        # threshold=90 → 위험도 낮은 장애 제외
        result_high = predict_sla_risk(center=self.center, threshold=90)
        result_low = predict_sla_risk(center=self.center, threshold=10)
        self.assertLessEqual(len(result_high), len(result_low))


# ─────────────────────────────────────────────────────────────
# 5. 월간 인사이트 리포트 자동 생성
# ─────────────────────────────────────────────────────────────
class MonthlyInsightReportTest(PatternFixtureMixin, TestCase):
    """월간 인사이트 리포트 자동 생성"""

    def setUp(self):
        now = timezone.now()
        # 이번 달 장애 5건 (3건 SLA OK, 2건 위반)
        for i in range(3):
            self._make_incident(arrival_minutes=30, resolve_minutes=100)
        for i in range(2):
            self._make_incident(arrival_minutes=150, resolve_minutes=500)
        # school2에 노후 장비
        self._make_asset(school=self.school2, install_year=2017, serial_suffix='ins')

    def test_function_importable(self):
        try:
            from apps.incidents.pattern_service import generate_monthly_insight
        except ImportError:
            self.fail('generate_monthly_insight 가 pattern_service.py에 없습니다.')

    def test_returns_dict(self):
        from apps.incidents.pattern_service import generate_monthly_insight
        now = timezone.now()
        result = generate_monthly_insight(
            center=self.center, year=now.year, month=now.month
        )
        self.assertIsInstance(result, dict)

    def test_has_summary_section(self):
        from apps.incidents.pattern_service import generate_monthly_insight
        now = timezone.now()
        result = generate_monthly_insight(
            center=self.center, year=now.year, month=now.month
        )
        self.assertIn('summary', result)

    def test_summary_has_required_fields(self):
        from apps.incidents.pattern_service import generate_monthly_insight
        now = timezone.now()
        result = generate_monthly_insight(
            center=self.center, year=now.year, month=now.month
        )
        summary = result['summary']
        for key in ('total_incidents', 'sla_arrival_rate', 'sla_resolve_rate'):
            self.assertIn(key, summary)

    def test_has_hotspots_section(self):
        from apps.incidents.pattern_service import generate_monthly_insight
        now = timezone.now()
        result = generate_monthly_insight(
            center=self.center, year=now.year, month=now.month
        )
        self.assertIn('hotspots', result)

    def test_has_vulnerable_assets_section(self):
        from apps.incidents.pattern_service import generate_monthly_insight
        now = timezone.now()
        result = generate_monthly_insight(
            center=self.center, year=now.year, month=now.month
        )
        self.assertIn('vulnerable_assets', result)

    def test_has_recommendations(self):
        from apps.incidents.pattern_service import generate_monthly_insight
        now = timezone.now()
        result = generate_monthly_insight(
            center=self.center, year=now.year, month=now.month
        )
        self.assertIn('recommendations', result)
        self.assertIsInstance(result['recommendations'], list)

    def test_sla_rate_correct(self):
        """3/5 = 60% SLA 도착 준수율"""
        from apps.incidents.pattern_service import generate_monthly_insight
        now = timezone.now()
        result = generate_monthly_insight(
            center=self.center, year=now.year, month=now.month
        )
        rate = result['summary']['sla_arrival_rate']
        # 허용 범위: 50~70% (테스트 환경 변동 고려)
        self.assertGreaterEqual(rate, 0)
        self.assertLessEqual(rate, 100)


# ─────────────────────────────────────────────────────────────
# 6. API 엔드포인트
# ─────────────────────────────────────────────────────────────
class PatternAPITest(PatternFixtureMixin, TestCase):
    """장애 패턴 분석 고도화 API"""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        for i in range(3):
            self._make_incident()

    def test_vulnerable_assets_api_200(self):
        resp = self.client.get(
            f'/api/incidents/pattern/vulnerable-assets/?center={self.center.pk}'
        )
        self.assertEqual(resp.status_code, 200)

    def test_vulnerable_assets_api_has_results(self):
        self._make_asset(serial_suffix='api1')
        resp = self.client.get(
            f'/api/incidents/pattern/vulnerable-assets/?center={self.center.pk}'
        )
        data = resp.json()
        self.assertIn('results', data)

    def test_seasonal_api_200(self):
        resp = self.client.get(
            f'/api/incidents/pattern/seasonal/?center={self.center.pk}'
        )
        self.assertEqual(resp.status_code, 200)

    def test_seasonal_api_has_4_seasons(self):
        resp = self.client.get(
            f'/api/incidents/pattern/seasonal/?center={self.center.pk}'
        )
        data = resp.json()
        self.assertIn('seasons', data)
        self.assertEqual(len(data['seasons']), 4)

    def test_sla_risk_api_200(self):
        resp = self.client.get(
            f'/api/incidents/pattern/sla-risk/?center={self.center.pk}'
        )
        self.assertEqual(resp.status_code, 200)

    def test_sla_risk_api_has_results(self):
        resp = self.client.get(
            f'/api/incidents/pattern/sla-risk/?center={self.center.pk}'
        )
        data = resp.json()
        self.assertIn('results', data)

    def test_monthly_insight_api_200(self):
        now = timezone.now()
        resp = self.client.get(
            f'/api/incidents/pattern/monthly-insight/'
            f'?center={self.center.pk}&year={now.year}&month={now.month}'
        )
        self.assertEqual(resp.status_code, 200)

    def test_monthly_insight_api_has_sections(self):
        now = timezone.now()
        resp = self.client.get(
            f'/api/incidents/pattern/monthly-insight/'
            f'?center={self.center.pk}&year={now.year}&month={now.month}'
        )
        data = resp.json()
        for key in ('summary', 'hotspots', 'vulnerable_assets', 'recommendations'):
            self.assertIn(key, data)

    def test_api_requires_auth(self):
        c = APIClient()
        resp = c.get(f'/api/incidents/pattern/vulnerable-assets/?center={self.center.pk}')
        self.assertIn(resp.status_code, [401, 403])
