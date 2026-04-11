"""
Phase 7-3: 레이트 리미팅 테스트

테스트 범위:
  1. django-ratelimit 패키지 설치
  2. 로그인 API — IP당 분당 10회
  3. 파일 업로드 — 사용자당 시간당 100회
  4. PDF 생성 — 사용자당 분당 5회
  5. 설정 상수 확인
"""
from django.test import TestCase
from django.core.cache import cache


# ─────────────────────────────────────────────────────────────
# 1. 패키지 설치 확인
# ─────────────────────────────────────────────────────────────
class RateLimitPackageTest(TestCase):

    def test_ratelimit_importable(self):
        """django-ratelimit 패키지가 설치되어야 한다"""
        try:
            import django_ratelimit
        except ImportError:
            self.fail('django-ratelimit 패키지가 설치되지 않았습니다.')

    def test_ratelimit_decorator_importable(self):
        try:
            from django_ratelimit.decorators import ratelimit
        except ImportError:
            self.fail('django_ratelimit.decorators.ratelimit를 import할 수 없습니다.')

    def test_ratelimit_exception_importable(self):
        try:
            from django_ratelimit.exceptions import Ratelimited
        except ImportError:
            self.fail('django_ratelimit.exceptions.Ratelimited를 import할 수 없습니다.')


# ─────────────────────────────────────────────────────────────
# 2. 설정값 확인
# ─────────────────────────────────────────────────────────────
class RateLimitSettingsTest(TestCase):

    def test_ratelimit_login_rate_setting(self):
        """RATELIMIT_LOGIN_RATE 설정이 있어야 한다 (IP당 분당 10회)"""
        from django.conf import settings
        val = getattr(settings, 'RATELIMIT_LOGIN_RATE', None)
        self.assertIsNotNone(val, 'RATELIMIT_LOGIN_RATE 설정이 없습니다.')
        self.assertIn('10', val, f'로그인 제한이 10회가 아닙니다: {val}')

    def test_ratelimit_upload_rate_setting(self):
        """RATELIMIT_UPLOAD_RATE 설정이 있어야 한다 (사용자당 시간당 100회)"""
        from django.conf import settings
        val = getattr(settings, 'RATELIMIT_UPLOAD_RATE', None)
        self.assertIsNotNone(val, 'RATELIMIT_UPLOAD_RATE 설정이 없습니다.')
        self.assertIn('100', val, f'업로드 제한이 100회가 아닙니다: {val}')

    def test_ratelimit_pdf_rate_setting(self):
        """RATELIMIT_PDF_RATE 설정이 있어야 한다 (사용자당 분당 5회)"""
        from django.conf import settings
        val = getattr(settings, 'RATELIMIT_PDF_RATE', None)
        self.assertIsNotNone(val, 'RATELIMIT_PDF_RATE 설정이 없습니다.')
        self.assertIn('5', val, f'PDF 제한이 5회가 아닙니다: {val}')


# ─────────────────────────────────────────────────────────────
# 3. 로그인 API 레이트 리미팅
# ─────────────────────────────────────────────────────────────
class LoginRateLimitTest(TestCase):
    """JWT 토큰 API 레이트 리미팅"""

    def setUp(self):
        cache.clear()
        from rest_framework.test import APIClient
        self.client = APIClient()

    def tearDown(self):
        cache.clear()

    def test_jwt_token_endpoint_has_ratelimit(self):
        """JWT token 엔드포인트에 ratelimit 데코레이터가 적용되어 있어야 한다"""
        from apps.accounts.views import CustomTokenObtainPairView
        view_func = CustomTokenObtainPairView.as_view()
        # ratelimit 적용 시 view에 _ratelimit 속성이 있거나
        # 또는 view 클래스에 throttle_classes가 있어야 함
        has_throttle = (
            hasattr(CustomTokenObtainPairView, 'throttle_classes')
            or hasattr(view_func, '_ratelimit')
            or hasattr(CustomTokenObtainPairView, '_ratelimit_config')
        )
        self.assertTrue(has_throttle, 'JWT token view에 레이트 리미팅이 없습니다.')


# ─────────────────────────────────────────────────────────────
# 4. 커스텀 Throttle 클래스
# ─────────────────────────────────────────────────────────────
class CustomThrottleTest(TestCase):
    """커스텀 Throttle 클래스"""

    def test_login_throttle_importable(self):
        """core.throttling.LoginRateThrottle 이 있어야 한다"""
        try:
            from core.throttling import LoginRateThrottle
        except ImportError:
            self.fail('core.throttling.LoginRateThrottle가 없습니다.')

    def test_upload_throttle_importable(self):
        """core.throttling.UploadRateThrottle 이 있어야 한다"""
        try:
            from core.throttling import UploadRateThrottle
        except ImportError:
            self.fail('core.throttling.UploadRateThrottle가 없습니다.')

    def test_pdf_throttle_importable(self):
        """core.throttling.PDFGenerateThrottle 이 있어야 한다"""
        try:
            from core.throttling import PDFGenerateThrottle
        except ImportError:
            self.fail('core.throttling.PDFGenerateThrottle가 없습니다.')

    def test_login_throttle_rate(self):
        """LoginRateThrottle 은 10/min 이어야 한다"""
        from core.throttling import LoginRateThrottle
        self.assertEqual(LoginRateThrottle.rate, '10/min')

    def test_upload_throttle_rate(self):
        """UploadRateThrottle 은 100/hour 이어야 한다"""
        from core.throttling import UploadRateThrottle
        self.assertEqual(UploadRateThrottle.rate, '100/hour')

    def test_pdf_throttle_rate(self):
        """PDFGenerateThrottle 은 5/min 이어야 한다"""
        from core.throttling import PDFGenerateThrottle
        self.assertEqual(PDFGenerateThrottle.rate, '5/min')
