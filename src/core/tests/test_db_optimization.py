"""
Phase 6-1: DB 쿼리 최적화 테스트

테스트 범위:
  1. Incident 모델 — DB 인덱스 추가 확인
  2. 통계/대시보드 뷰 — Redis 캐시 5분 TTL 적용
  3. django-debug-toolbar 개발환경 설치 확인
  4. 느린 쿼리 로그 설정 (> 100ms) 확인
"""
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.schools.models import SupportCenter, SchoolType, School


# ─────────────────────────────────────────────────────────────
# 캐시 무효화용 LocMem 설정
# ─────────────────────────────────────────────────────────────
LOCMEM_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'test-cache',
    }
}

NO_THROTTLE = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}


# ─────────────────────────────────────────────────────────────
# 1. Incident DB 인덱스 확인
# ─────────────────────────────────────────────────────────────
class IncidentIndexTest(TestCase):
    """Incident 모델에 필수 DB 인덱스가 정의되어야 한다"""

    def _index_fields(self):
        from apps.incidents.models import Incident
        return [list(idx.fields) for idx in Incident._meta.indexes]

    def test_has_received_at_index(self):
        """received_at 단독 인덱스"""
        fields_list = self._index_fields()
        self.assertIn(['received_at'], fields_list)

    def test_has_category_received_at_index(self):
        """(category_id, received_at) 복합 인덱스"""
        fields_list = self._index_fields()
        self.assertIn(['category', 'received_at'], fields_list)

    def test_has_school_status_index(self):
        """기존 (school, status) 인덱스 유지"""
        fields_list = self._index_fields()
        self.assertIn(['school', 'status'], fields_list)

    def test_has_status_received_at_index(self):
        """기존 (status, received_at) 인덱스 유지"""
        fields_list = self._index_fields()
        self.assertIn(['status', 'received_at'], fields_list)


# ─────────────────────────────────────────────────────────────
# 2. 통계/대시보드 캐시 적용 확인
# ─────────────────────────────────────────────────────────────
class TrendCacheTest(TestCase):
    """통계 trend 엔드포인트 — Redis 5분 캐시 적용"""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='stat_admin', email='stat_admin@test.com',
            password='pass', role='admin',
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    @override_settings(CACHES=LOCMEM_CACHE, REST_FRAMEWORK=NO_THROTTLE)
    def test_trend_cache_is_set(self):
        """trend 호출 시 캐시 키 stats_trend_30d 가 저장되어야 한다"""
        from django.core.cache import cache
        cache.clear()
        self.client.get('/api/statistics/daily/trend/')
        self.assertIsNotNone(
            cache.get('stats_trend_30d'),
            'cache에 stats_trend_30d 키가 없습니다.'
        )

    @override_settings(CACHES=LOCMEM_CACHE, REST_FRAMEWORK=NO_THROTTLE)
    def test_trend_second_call_uses_cache(self):
        """두 번째 trend 호출은 캐시에서 반환되어야 한다"""
        from django.core.cache import cache
        cache.clear()
        resp1 = self.client.get('/api/statistics/daily/trend/')
        self.assertEqual(resp1.status_code, 200)
        # 캐시 키가 존재하면 두 번째 호출은 DB 없이 동일 응답
        resp2 = self.client.get('/api/statistics/daily/trend/')
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp1.json(), resp2.json())


class PatternCacheTest(TestCase):
    """패턴 분석 API — Redis 5분 캐시 적용"""

    @classmethod
    def setUpTestData(cls):
        cls.center = SupportCenter.objects.create(code='cache_ctr', name='캐시테스트청')
        cls.admin = User.objects.create_user(
            username='pattern_admin', email='pattern_admin@test.com',
            password='pass', role='admin',
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    @override_settings(CACHES=LOCMEM_CACHE, REST_FRAMEWORK=NO_THROTTLE)
    def test_seasonal_api_cache_set(self):
        """seasonal pattern API 호출 시 캐시 키가 저장되어야 한다"""
        from django.core.cache import cache
        cache.clear()
        self.client.get(
            f'/api/incidents/pattern/seasonal/?center={self.center.pk}'
        )
        cache_key = f'pattern_seasonal_{self.center.pk}_'
        self.assertIsNotNone(
            cache.get(cache_key),
            f'캐시에 {cache_key} 키가 없습니다.'
        )

    @override_settings(CACHES=LOCMEM_CACHE, REST_FRAMEWORK=NO_THROTTLE)
    def test_monthly_insight_cache_set(self):
        """monthly insight API 호출 시 캐시 키가 저장되어야 한다"""
        from django.core.cache import cache
        from django.utils import timezone
        cache.clear()
        now = timezone.now()
        self.client.get(
            f'/api/incidents/pattern/monthly-insight/?center={self.center.pk}'
        )
        cache_key = f'pattern_monthly_insight_{self.center.pk}_{now.year}_{now.month}'
        self.assertIsNotNone(
            cache.get(cache_key),
            f'캐시에 {cache_key} 키가 없습니다.'
        )


class ComprehensiveStatsCacheTest(TestCase):
    """comprehensive_stats_api — Redis 5분 캐시 적용"""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(
            username='comp_admin', email='comp_admin@test.com',
            password='pass', role='admin',
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    @override_settings(CACHES=LOCMEM_CACHE, REST_FRAMEWORK=NO_THROTTLE)
    def test_comprehensive_stats_cache_set(self):
        """comprehensive_stats_api 호출 시 캐시 키가 저장되어야 한다"""
        from django.core.cache import cache
        cache.clear()
        year = timezone.now().year
        self.client.get(f'/api/statistics/comprehensive/?year={year}')
        cache_key = f'comprehensive_stats_{year}_None'
        self.assertIsNotNone(
            cache.get(cache_key),
            f'캐시에 {cache_key} 키가 없습니다.'
        )

    @override_settings(CACHES=LOCMEM_CACHE, REST_FRAMEWORK=NO_THROTTLE)
    def test_comprehensive_stats_second_call_cached(self):
        """두 번째 comprehensive_stats 호출은 캐시에서 반환"""
        from django.core.cache import cache
        cache.clear()
        year = timezone.now().year
        resp1 = self.client.get(f'/api/statistics/comprehensive/?year={year}')
        resp2 = self.client.get(f'/api/statistics/comprehensive/?year={year}')
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp2.status_code, 200)


# ─────────────────────────────────────────────────────────────
# 3. django-debug-toolbar 설치 확인
# ─────────────────────────────────────────────────────────────
class DebugToolbarTest(TestCase):
    """django-debug-toolbar 개발환경 설치"""

    def test_debug_toolbar_in_requirements(self):
        """requirements.txt에 django-debug-toolbar 포함"""
        from django.conf import settings
        import os
        req_path = os.path.join(str(settings.BASE_DIR), 'requirements.txt')
        with open(req_path) as f:
            content = f.read().lower()
        self.assertIn('django-debug-toolbar', content)

    def test_debug_toolbar_importable(self):
        """debug_toolbar 모듈 임포트 가능해야 함"""
        try:
            import debug_toolbar
        except ImportError:
            self.fail('django-debug-toolbar 패키지가 설치되지 않았습니다.')

    def test_internal_ips_configured(self):
        """INTERNAL_IPS 설정이 존재해야 함"""
        from django.conf import settings
        self.assertTrue(hasattr(settings, 'INTERNAL_IPS'))
        self.assertIn('127.0.0.1', settings.INTERNAL_IPS)


# ─────────────────────────────────────────────────────────────
# 4. 느린 쿼리 로그 설정 확인 (> 100ms)
# ─────────────────────────────────────────────────────────────
class SlowQueryLogTest(TestCase):
    """느린 쿼리 로깅 설정"""

    def test_slow_query_threshold_setting_exists(self):
        """SLOW_QUERY_LOG_MS 설정이 100ms로 존재해야 함"""
        from django.conf import settings
        self.assertTrue(
            hasattr(settings, 'SLOW_QUERY_LOG_MS'),
            'SLOW_QUERY_LOG_MS 설정이 없습니다.'
        )
        self.assertEqual(settings.SLOW_QUERY_LOG_MS, 100)

    def test_db_backends_logger_configured(self):
        """LOGGING에 django.db.backends 로거가 설정되어야 함"""
        from django.conf import settings
        loggers = settings.LOGGING.get('loggers', {})
        self.assertIn(
            'django.db.backends', loggers,
            'LOGGING에 django.db.backends 항목이 없습니다.'
        )

    def test_db_backends_logger_debug_level(self):
        """django.db.backends 로거 레벨이 DEBUG이어야 함"""
        from django.conf import settings
        level = settings.LOGGING.get('loggers', {}).get(
            'django.db.backends', {}
        ).get('level', 'WARNING')
        self.assertEqual(level, 'DEBUG')
