"""
Phase 7-2: 인증/권한 강화 테스트

테스트 범위:
  1. JWT 설정 (토큰 만료, 회전, 블랙리스트)
  2. 비밀번호 복잡도 검증
  3. JWT API 로그인 실패 잠금
  4. 동시 로그인 제한
  5. 2FA 모델 필드 + TOTP 검증
"""
import io
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import User, UserSession


def make_user(username='testuser', role='worker', **kwargs):
    user = User.objects.create_user(
        username=username,
        email=f'{username}@test.com',
        name='테스트',
        password='TestPass1!',
        role=role,
        **kwargs,
    )
    return user


# ─────────────────────────────────────────────────────────────
# 1. JWT 설정
# ─────────────────────────────────────────────────────────────
class JWTSettingsTest(TestCase):
    """SIMPLE_JWT 설정이 올바르게 되어 있어야 한다"""

    def test_simple_jwt_access_token_lifetime_is_short(self):
        """access token 만료가 1시간 이하여야 한다"""
        from django.conf import settings
        jwt_conf = getattr(settings, 'SIMPLE_JWT', {})
        lifetime = jwt_conf.get('ACCESS_TOKEN_LIFETIME', timedelta(minutes=5))
        self.assertLessEqual(
            lifetime.total_seconds(), 3600,
            f'ACCESS_TOKEN_LIFETIME이 1시간 초과: {lifetime}'
        )

    def test_simple_jwt_rotate_refresh_tokens(self):
        """리프레시 토큰 회전이 활성화되어야 한다"""
        from django.conf import settings
        jwt_conf = getattr(settings, 'SIMPLE_JWT', {})
        self.assertTrue(
            jwt_conf.get('ROTATE_REFRESH_TOKENS', False),
            'ROTATE_REFRESH_TOKENS가 True가 아닙니다.'
        )

    def test_simple_jwt_blacklist_after_rotation(self):
        """사용된 리프레시 토큰이 블랙리스트에 추가되어야 한다"""
        from django.conf import settings
        jwt_conf = getattr(settings, 'SIMPLE_JWT', {})
        self.assertTrue(
            jwt_conf.get('BLACKLIST_AFTER_ROTATION', False),
            'BLACKLIST_AFTER_ROTATION이 True가 아닙니다.'
        )

    def test_token_blacklist_in_installed_apps(self):
        """rest_framework_simplejwt.token_blacklist 앱이 등록되어야 한다"""
        from django.conf import settings
        self.assertIn(
            'rest_framework_simplejwt.token_blacklist',
            settings.INSTALLED_APPS,
            'token_blacklist 앱이 INSTALLED_APPS에 없습니다.'
        )

    def test_simple_jwt_refresh_token_lifetime(self):
        """refresh token 만료가 30일 이하여야 한다"""
        from django.conf import settings
        jwt_conf = getattr(settings, 'SIMPLE_JWT', {})
        lifetime = jwt_conf.get('REFRESH_TOKEN_LIFETIME', timedelta(days=1))
        self.assertLessEqual(
            lifetime.total_seconds(), 30 * 24 * 3600,
            f'REFRESH_TOKEN_LIFETIME이 30일 초과: {lifetime}'
        )


# ─────────────────────────────────────────────────────────────
# 2. 비밀번호 복잡도
# ─────────────────────────────────────────────────────────────
class PasswordComplexityTest(TestCase):
    """비밀번호 복잡도 검증"""

    def test_complexity_validator_importable(self):
        try:
            from core.validators import PasswordComplexityValidator
        except ImportError:
            self.fail('core.validators.PasswordComplexityValidator가 없습니다.')

    def test_password_without_uppercase_rejected(self):
        """대문자 없는 비밀번호 거부"""
        from core.validators import PasswordComplexityValidator
        from django.core.exceptions import ValidationError
        validator = PasswordComplexityValidator()
        with self.assertRaises(ValidationError):
            validator.validate('testpass1!')

    def test_password_without_digit_rejected(self):
        """숫자 없는 비밀번호 거부"""
        from core.validators import PasswordComplexityValidator
        from django.core.exceptions import ValidationError
        validator = PasswordComplexityValidator()
        with self.assertRaises(ValidationError):
            validator.validate('TestPass!!')

    def test_password_without_special_char_rejected(self):
        """특수문자 없는 비밀번호 거부"""
        from core.validators import PasswordComplexityValidator
        from django.core.exceptions import ValidationError
        validator = PasswordComplexityValidator()
        with self.assertRaises(ValidationError):
            validator.validate('TestPass12')

    def test_valid_complex_password_passes(self):
        """대문자+숫자+특수문자 포함 비밀번호 통과"""
        from core.validators import PasswordComplexityValidator
        validator = PasswordComplexityValidator()
        # 예외가 발생하지 않아야 함
        validator.validate('TestPass1!')

    def test_complexity_validator_in_auth_password_validators(self):
        """settings.AUTH_PASSWORD_VALIDATORS에 PasswordComplexityValidator가 있어야 한다"""
        from django.conf import settings
        names = [v['NAME'] for v in settings.AUTH_PASSWORD_VALIDATORS]
        self.assertTrue(
            any('PasswordComplexityValidator' in n for n in names),
            'AUTH_PASSWORD_VALIDATORS에 PasswordComplexityValidator가 없습니다.'
        )


# ─────────────────────────────────────────────────────────────
# 3. JWT API 로그인 실패 잠금
# ─────────────────────────────────────────────────────────────
class JWTLoginLockoutTest(TestCase):
    """JWT API /api/accounts/token/ 도 5회 실패 시 잠금"""

    def setUp(self):
        self.client = APIClient()
        self.user = make_user(username='locktest')
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_jwt_login_success(self):
        """올바른 자격증명으로 JWT 토큰 발급"""
        resp = self.client.post('/api/accounts/token/', {
            'username': 'locktest',
            'password': 'TestPass1!',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('access', resp.data)

    def test_jwt_5_failures_locks_account(self):
        """JWT API 5회 실패 시 429 또는 400(잠금 메시지) 반환"""
        for i in range(5):
            self.client.post('/api/accounts/token/', {
                'username': 'locktest',
                'password': 'WrongPass!1',
            }, format='json')

        # 6번째: 잠금 상태 확인
        resp = self.client.post('/api/accounts/token/', {
            'username': 'locktest',
            'password': 'TestPass1!',
        }, format='json')
        # 잠금 시 400 또는 429
        self.assertIn(resp.status_code, [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_429_TOO_MANY_REQUESTS,
        ], f'잠금 후 응답코드가 예상과 다름: {resp.status_code}')


# ─────────────────────────────────────────────────────────────
# 4. 동시 로그인 제한
# ─────────────────────────────────────────────────────────────
class ConcurrentLoginLimitTest(TestCase):
    """동시 로그인 세션 제한"""

    def test_max_concurrent_sessions_setting_exists(self):
        """settings.MAX_CONCURRENT_SESSIONS 가 정의되어야 한다"""
        from django.conf import settings
        val = getattr(settings, 'MAX_CONCURRENT_SESSIONS', None)
        self.assertIsNotNone(val, 'MAX_CONCURRENT_SESSIONS 설정이 없습니다.')
        self.assertGreater(val, 0)

    def test_concurrent_session_limit_enforced(self):
        """MAX_CONCURRENT_SESSIONS 초과 시 가장 오래된 세션 비활성화"""
        from django.conf import settings
        user = make_user(username='concurrenttest')
        limit = getattr(settings, 'MAX_CONCURRENT_SESSIONS', 3)

        # 제한+1 개 세션 생성
        for i in range(limit + 1):
            UserSession.objects.create(
                user=user,
                session_key=f'sess_{i}',
                is_active=True,
            )

        from apps.accounts.services import enforce_concurrent_session_limit
        enforce_concurrent_session_limit(user)

        active_count = UserSession.objects.filter(user=user, is_active=True).count()
        self.assertLessEqual(active_count, limit,
            f'활성 세션이 제한({limit})을 초과: {active_count}')


# ─────────────────────────────────────────────────────────────
# 5. 2FA 모델 필드 + TOTP
# ─────────────────────────────────────────────────────────────
class TwoFactorAuthTest(TestCase):
    """2FA TOTP 기능"""

    def test_user_has_2fa_fields(self):
        """User 모델에 is_2fa_enabled, totp_secret 필드가 있어야 한다"""
        user = make_user(username='tfauser')
        self.assertTrue(hasattr(user, 'is_2fa_enabled'), 'is_2fa_enabled 필드 없음')
        self.assertTrue(hasattr(user, 'totp_secret'),    'totp_secret 필드 없음')

    def test_2fa_disabled_by_default(self):
        """기본적으로 2FA는 비활성화"""
        user = make_user(username='tfa2user')
        self.assertFalse(user.is_2fa_enabled)

    def test_totp_verify_api_exists(self):
        """2FA 설정/검증 API URL이 있어야 한다"""
        from django.urls import reverse, NoReverseMatch
        try:
            reverse('accounts:2fa-setup')
        except NoReverseMatch:
            self.fail('accounts:2fa-setup URL이 없습니다.')

    def test_pyotp_importable(self):
        """pyotp 패키지가 설치되어야 한다"""
        try:
            import pyotp
        except ImportError:
            self.fail('pyotp 패키지가 설치되지 않았습니다.')

    def test_totp_token_validates(self):
        """pyotp로 발급한 TOTP 코드가 검증되어야 한다"""
        import pyotp
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        code = totp.now()
        self.assertTrue(totp.verify(code))
